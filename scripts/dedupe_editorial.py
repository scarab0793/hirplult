#!/usr/bin/env python3
"""Merge duplicate stories in data/editorial.json. No network, no AI, safe to run again and again.

The same event can be written up more than once (for example when outlets report it hours
apart). This script finds such articles by content (see hp_dedupe.py), keeps the best one,
adds the other reports' sources to it and drops the rest. It also attaches plain RSS reports
from data/news.json to the finished article that already tells the same story, so the page
does not list them a second time. Only articles born from RSS (ids starting with "rss-") are
touched, never the hand-written catalog overrides. data/news.json is only read.
"""
import json
from pathlib import Path

import hp_dedupe

EDITORIAL = Path("data/editorial.json")
NEWS = Path("data/news.json")


def merge_once(items):
    pool = [x for x in items if x.get("ai_edited") and str(x.get("id", "")).startswith("rss-") and x.get("published_at")]
    index = hp_dedupe.Index(pool)
    dropped, report = set(), []
    for group in hp_dedupe.clusters(index, pool):
        if len(group) < 2:
            continue
        keep = hp_dedupe.keeper(group)
        others = [x for x in group if x is not keep]
        hp_dedupe.merge_into(keep, others)
        dropped.update(id(x) for x in others)
        report.append((keep, others))
    return [x for x in items if id(x) not in dropped], report


def merge_duplicates(items, passes=3):
    """Merge duplicate articles. Returns (kept items, list of (kept article, dropped articles)).

    Once duplicates are gone the words are weighed again, and a pair that was just under the threshold
    can reach it. Passes repeat until nothing merges (at most `passes`), so one run ends in a state
    that the next run leaves alone."""
    report = []
    for _ in range(passes):
        items, merged = merge_once(items)
        if not merged:
            break
        report.extend(merged)
    return items, report


def read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def main():
    if not EDITORIAL.exists():
        print("No editorial.json to check.")
        return
    archive = read(EDITORIAL, {"items": []})
    items = archive.get("items", [])
    before = json.dumps(items, ensure_ascii=False, sort_keys=True)
    kept, report = merge_duplicates(items)
    for keep, others in report:
        print(f"Merged {len(others)} duplicate(s) into: {keep['t'][:90]}")
        for other in others:
            print(f"   dropped: {other['t'][:90]}")
    # Plain RSS reports of a story that already has a finished article become sources of that article.
    ids = {x["id"] for x in kept}
    reports = [x for x in read(NEWS, {"items": []}).get("items", []) if x.get("id") not in ids and not x.get("ai_edited")]
    attached, _ = hp_dedupe.attach_reports(kept, reports)
    if attached:
        print(f"Attached {attached} plain RSS report(s) to existing articles")
    archive["items"] = kept
    if json.dumps(kept, ensure_ascii=False, sort_keys=True) != before:
        EDITORIAL.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Articles: {len(items)} -> {len(kept)}; merged groups: {len(report)}; attached reports: {attached}")


if __name__ == "__main__":
    main()
