#!/usr/bin/env python3
"""Collect international RSS headlines into data/world/queue.json (no AI)."""
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
import world_config as cfg  # noqa: E402
from fetch_news import child, clean, feed_image, parse_date  # noqa: E402

QUEUE = Path("data/world/queue.json")


def collect(outlet, feed, hosts, section, now):
    request = urllib.request.Request(feed, headers={"User-Agent": "HirpultWorldBot/1.0 (+https://hirpult.com)"})
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read(2_500_000))
    rows = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] not in ("item", "entry"):
            continue
        title = clean(child(node, "title"))
        link = child(node, "link").strip()
        if not link:
            for e in node:
                if e.tag.rsplit("}", 1)[-1] == "link" and e.attrib.get("href"):
                    link = e.attrib["href"]
                    break
        host = (urlparse(link).hostname or "").lower().removeprefix("www.")
        if not any(host == h or host.endswith("." + h) for h in hosts):
            continue
        date = parse_date(child(node, "pubDate") or child(node, "published") or child(node, "updated") or child(node, "date"))
        if date is None or not title:
            continue
        if date.tzinfo is None:
            date = date.replace(tzinfo=dt.timezone.utc)
        date = date.astimezone(dt.timezone.utc)
        age = (now - date).total_seconds()
        if age < -3600 or age > cfg.HOURS * 3600:
            continue
        summary = clean(child(node, "description") or child(node, "summary") or child(node, "content"))[:450]
        if len(summary) < 25:
            summary = title
        image = feed_image(node)
        link = link.split("?")[0] if "bbc." in host else link
        rows.append({
            "id": "w-" + hashlib.sha256(link.encode()).hexdigest()[:16],
            "outlet": outlet, "section": section, "published_at": date.isoformat(),
            "title": title, "summary": summary, "url": link, "img": image,
        })
    return rows


def main():
    now = dt.datetime.now(dt.timezone.utc)
    old = []
    if QUEUE.exists():
        try:
            old = json.loads(QUEUE.read_text(encoding="utf-8")).get("items", [])
        except (ValueError, OSError):
            pass
    gathered, ok, failed = [], set(), []
    for outlet, feed, hosts, section in cfg.SOURCES:
        try:
            rows = collect(outlet, feed, hosts, section, now)
            gathered.extend(rows)
            ok.add(outlet)
        except Exception as exc:  # one broken feed must not stop the rest
            failed.append(f"{outlet} {feed.split('/')[-2] if '/' in feed else feed}: {type(exc).__name__}")
    if not ok:
        raise RuntimeError("All world feeds failed: " + "; ".join(failed[:6]))
    unique = {}
    for item in old + gathered:  # fresh data wins
        if (now - dt.datetime.fromisoformat(item["published_at"])).total_seconds() <= cfg.HOURS * 3600:
            unique[item["id"]] = item
    rows = sorted(unique.values(), key=lambda x: x["published_at"], reverse=True)[: cfg.QUEUE_LIMIT]
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps({"updated_at": now.isoformat(), "outlets_ok": sorted(ok), "failed": failed, "items": rows},
                                ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"World queue: {len(rows)} headlines; outlets OK: {sorted(ok)}; failed feeds: {len(failed)}")


if __name__ == "__main__":
    main()
