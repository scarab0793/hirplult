#!/usr/bin/env python3
"""Translate the English master articles into the configured languages (data/world/i18n/<lang>.json)."""
import datetime as dt
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import hp_ai  # noqa: E402
import world_config as cfg  # noqa: E402
from world_write import read, write, ARTICLES, STATE  # noqa: E402

I18N = Path("data/world/i18n")
MANIFEST = Path("data/world/manifest.json")
MAX_TRIES = 2


def main():
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    articles = read(ARTICLES, {"items": []})["items"]
    state = read(STATE, {"failed": {}, "failed_translations": {}})
    bad = state.setdefault("failed_translations", {})
    live = {x["id"] for x in articles}
    tables = {lang: read(I18N / f"{lang}.json", {}) for lang in cfg.LANGS}
    for lang in tables:  # drop translations of articles that left the page
        tables[lang] = {k: v for k, v in tables[lang].items() if k in live}
    jobs = []
    for master in articles:  # newest first
        for lang in cfg.LANGS:
            tag = f"{master['id']}:{lang}"
            if master["id"] not in tables[lang] and bad.get(tag, 0) < MAX_TRIES:
                jobs.append((master, lang, tag))
    limit = int(os.getenv("HIRPULT_WORLD_MAX_TRANSLATIONS", "160"))
    jobs = jobs[:limit]
    translated = 0
    if key and jobs:
        def work(job):
            master, lang, tag = job
            try:
                return job, hp_ai.translate_article(master, lang, key), None
            except Exception as exc:  # one bad article must not stop the others
                return job, None, exc

        stop = False
        with ThreadPoolExecutor(max_workers=6) as pool:
            for (master, lang, tag), out, error in pool.map(work, jobs):
                if error is not None:
                    if isinstance(error, hp_ai.ApiError):
                        print("API error:", error)
                        stop = stop or error.status in (400, 401, 402, 403, 404)
                    else:
                        bad[tag] = bad.get(tag, 0) + 1
                        print("Translation skipped:", tag, str(error)[:160])
                    continue
                tables[lang][master["id"]] = out
                bad.pop(tag, None)
                translated += 1
        if stop:
            print("Stopping: check the key, billing and model access.")
    state["failed_translations"] = {k: v for k, v in bad.items() if k.split(":")[0] in live}
    for lang, table in tables.items():
        write(I18N / f"{lang}.json", table)
    write(STATE, state)
    write(MANIFEST, {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "languages": ["en"] + [l for l in cfg.LANGS if tables[l]],
        "counts": {"en": len(articles), **{l: len(tables[l]) for l in cfg.LANGS}},
    })
    u = hp_ai.USAGE
    cost = u["input_tokens"] * 0.10 / 1e6 + u["output_tokens"] * 0.50 / 1e6
    print(f"Translations written: {translated} of {len(jobs)} tried; API calls: {u['calls']}; "
          f"tokens in/out: {u['input_tokens']}/{u['output_tokens']} (about ${cost:.3f})")


if __name__ == "__main__":
    main()
