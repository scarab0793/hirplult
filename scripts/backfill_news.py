#!/usr/bin/env python3
"""Optionally lengthen the original catalog stories from their sources.

Paused by default (HIRPULT_BACKFILL_BATCH=0): the catalog stories are already complete. When enabled,
it never touches RSS-born stories and never removes the "Amit érdemes tudni" or "Szubjektív nézőpont"
boxes a story already has. The title stays as it is; the lead and the body are rewritten and checked.
"""
import json
import os
from pathlib import Path

import hp_ai
from enrich_news import compose

SOURCE = Path("index.html")
DEST = Path("data/editorial.json")


def main():
    limit = max(0, min(3, int(os.getenv("HIRPULT_BACKFILL_BATCH", "0"))))
    if not limit:
        print("Backfill paused (HIRPULT_BACKFILL_BATCH=0).")
        return
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key or not SOURCE.exists():
        print("No API key or catalog; backfill skipped.")
        return
    html = SOURCE.read_text(encoding="utf-8")
    marker = "const items="
    start = html.find(marker)
    if start < 0:
        raise ValueError("Embedded article catalog not found")
    entries, _ = json.JSONDecoder().raw_decode(html[start + len(marker):].lstrip())
    old = json.loads(DEST.read_text(encoding="utf-8")) if DEST.exists() else {"items": []}
    completed = {x["id"] for x in old["items"]}
    count = 0
    for item in entries:
        if count >= limit:
            break
        if not item.get("id") or item["id"] in completed or item["id"].startswith("rss-"):
            continue
        group = [
            {"c": name, "t": item["t"], "s": item.get("s", ""), "src": [[name, url]]}
            for name, url in item.get("src", [])[:4]
            if isinstance(url, str) and url.startswith("https://")
        ]
        if not group:
            continue
        try:
            article = compose(group, key)
        except hp_ai.ApiError as exc:
            print("API error:", exc)
            break
        except ValueError as exc:
            print("Backfill skipped:", item["id"], str(exc)[:160])
            completed.add(item["id"])
            continue
        new = dict(item)
        new.update(s=article["lead"], p=article["paragraphs"], ai_edited=True)
        new["op"] = item.get("op") or article["op"]
        new["cav"] = item.get("cav") or article["cav"]
        old["items"].append(new)
        completed.add(item["id"])
        count += 1
    if count:
        DEST.parent.mkdir(parents=True, exist_ok=True)
        DEST.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Backfilled:", count, "Total:", len(old["items"]))


if __name__ == "__main__":
    main()
