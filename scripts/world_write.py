#!/usr/bin/env python3
"""Write English master articles for the Hirpult World edition from data/world/queue.json."""
import datetime as dt
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
import hp_ai  # noqa: E402
import world_config as cfg  # noqa: E402
from enrich_news import NoSource, source_text, words  # noqa: E402

QUEUE = Path("data/world/queue.json")
ARTICLES = Path("data/world/articles.json")
STATE = Path("data/world/state.json")
MAX_TRIES = 3
PER_SECTION = 3


def read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def similar(a, b):
    x, y = words(a["title"]), words(b["title"])
    return bool(x and y and len(x & y) >= 3 and len(x & y) / min(len(x), len(y)) >= 0.6)


def compose(group, key):
    evidence = []
    for item in group:
        evidence.append({
            "source": item["outlet"], "title": item["title"], "summary": item["summary"][:450],
            "published": item["published_at"][:10], "article_reference": source_text(item["url"]),
        })
    if not any(len(e["article_reference"]) >= 1200 for e in evidence):
        raise NoSource("not enough readable source text")
    return hp_ai.write_world_article(evidence, key)


def main():
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("No ANTHROPIC_API_KEY: nothing to write.")
        return
    now = dt.datetime.now(dt.timezone.utc)
    rows = read(QUEUE, {"items": []}).get("items", [])
    archive = read(ARTICLES, {"items": []})
    state = read(STATE, {"failed": {}, "failed_translations": {}})
    failed = state.setdefault("failed", {})
    done = {x["id"] for x in archive["items"]}
    for x in archive["items"]:
        done.update(x.get("member_ids", []))
    limit = max(0, min(30, int(os.getenv("HIRPULT_WORLD_MAX", "12"))))

    used, groups = set(), []
    for a in rows:
        if a["id"] in used or a["id"] in done or failed.get(a["id"], 0) >= MAX_TRIES:
            continue
        group = [a]
        used.add(a["id"])
        for b in rows:
            if b["id"] not in used and b["id"] not in done and b["outlet"] != a["outlet"] and similar(a, b):
                group.append(b)
                used.add(b["id"])
        groups.append(group)
    title_words = {x["id"]: words(x["title"]) for x in rows}

    def buzz(group):
        """Other outlets covering the same topic: the stories many outlets run come first."""
        shared = set()
        for a in group:
            for b in rows:
                if b["outlet"] != a["outlet"] and len(title_words[a["id"]] & title_words[b["id"]]) >= 2:
                    shared.add(b["outlet"])
        return max(len({x["outlet"] for x in group}) - 1, len(shared))

    groups.sort(key=lambda g: -min(buzz(g), 4))
    chosen, per_section = [], {}
    for group in groups:
        section = group[0]["section"]
        if per_section.get(section, 0) >= PER_SECTION:
            continue
        per_section[section] = per_section.get(section, 0) + 1
        chosen.append(group)
        if len(chosen) >= limit:
            break

    def work(group):
        try:
            return group, compose(group, key), None
        except Exception as exc:  # one bad article must not stop the others
            return group, None, exc

    written, stop = 0, False
    with ThreadPoolExecutor(max_workers=4) as pool:
        for group, article, error in pool.map(work, chosen):
            a = group[0]
            if error is not None:
                if isinstance(error, NoSource):
                    failed[a["id"]] = MAX_TRIES
                elif isinstance(error, hp_ai.ApiError):
                    print("API error:", error)
                    if error.status in (400, 401, 402, 403, 404, 429):
                        stop = True
                else:
                    failed[a["id"]] = failed.get(a["id"], 0) + 1
                    print("Article skipped:", a["id"], str(error)[:200])
                continue
            hosts = {(urlparse(x["url"]).hostname or "").removeprefix("www.") for x in group}
            donor = next((x for x in group if x.get("img")), None)
            record = {
                "id": a["id"], "member_ids": [x["id"] for x in group],
                "section": article["section"] or a["section"], "published_at": max(x["published_at"] for x in group),
                "t": article["title"][:180], "s": article["lead"][:500], "p": article["paragraphs"],
                "cav": article["cav"], "op": article["op"],
                "confirmed": len({x["outlet"] for x in group}) >= 2,
                "src": [[x["outlet"], x["url"]] for x in group],
            }
            if donor:
                record.update(img=donor["img"], img_outlet=donor["outlet"], img_link=donor["url"])
            archive["items"].append(record)
            failed.pop(a["id"], None)
            written += 1
    cutoff = now - dt.timedelta(days=cfg.KEEP_DAYS)
    archive["items"] = [x for x in archive["items"] if dt.datetime.fromisoformat(x["published_at"]) >= cutoff]
    archive["items"].sort(key=lambda x: x["published_at"], reverse=True)
    live = {x["id"] for x in rows}
    state["failed"] = {k: v for k, v in failed.items() if k in live}
    archive["updated_at"] = now.isoformat()
    write(ARTICLES, archive)
    write(STATE, state)
    u = hp_ai.USAGE
    cost = u["input_tokens"] * 0.10 / 1e6 + u["output_tokens"] * 0.50 / 1e6
    print(f"World articles written: {written}; skipped/failed: {len(chosen) - written}; API calls: {u['calls']}; "
          f"tokens in/out: {u['input_tokens']}/{u['output_tokens']} (about ${cost:.3f})" + ("; stopped early" if stop else ""))


if __name__ == "__main__":
    main()
