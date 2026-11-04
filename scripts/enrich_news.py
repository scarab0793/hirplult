#!/usr/bin/env python3
"""Turn fresh RSS stories into Hírpult articles with the Claude API.

For every story the script downloads the source article, asks Claude for an original
Hungarian article plus the "Amit érdemes tudni" and "Szubjektív nézőpont" boxes, checks the
result in code (numbers, quotations, word-for-word overlap, length) and stores it in
data/editorial.json. The page merges that file over the plain RSS records by id.
"""
import datetime as dt
import json
import os
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import hp_ai

NEWS = Path("data/news.json")
EDITORIAL = Path("data/editorial.json")
STATE = Path("data/ai-state.json")
KEEP_DAYS = int(os.getenv("HIRPULT_KEEP_DAYS", "10"))
MAX_TRIES = 3  # a story that fails the checks is retried in later runs; unreadable sources count as MAX_TRIES at once
# A story counts as "Megerősített" with two different publishers or one official source.
OFFICIAL_HOSTS = ("mnb.hu", "kormany.hu", "parlament.hu", "ksh.hu", "police.hu", "eurostat", "europa.eu", "mti.hu")
STOP = set("hogy mint után miatt szerint magyar most több egyik másik ezzel azzal között".split())


class NoSource(ValueError):
    """The source article could not be read (paywall, block, too short)."""


def words(s):
    return {w for w in re.findall(r"[a-záéíóöőúüű0-9]{4,}", s.lower()) if w not in STOP}


def similar(a, b):
    x, y = words(a["t"]), words(b["t"])
    return bool(x and y and len(x & y) >= 3 and len(x & y) / min(len(x), len(y)) >= 0.65)


class ArticleParser(HTMLParser):
    SKIP = ("script", "style", "nav", "footer", "aside", "header", "form", "svg")

    def __init__(self):
        super().__init__()
        self.ignore = 0
        self.capture = 0
        self.parts = []
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.ignore += 1
        if tag == "p" and not self.ignore:
            self.capture += 1
            self.buffer = []

    def handle_data(self, data):
        if self.capture and not self.ignore:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == "p" and self.capture:
            value = " ".join("".join(self.buffer).split())
            if 75 < len(value) < 2500:
                self.parts.append(value)
            self.capture = 0
            self.buffer = []
        if tag in self.SKIP and self.ignore:
            self.ignore -= 1


def source_text(url):
    """Paragraphs of the source article, used only as evidence and never republished."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; HirpultNewsBot/1.0; +https://hirplult.info)", "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            if "html" not in response.headers.get("Content-Type", ""):
                return ""
            raw = response.read(650000).decode("utf-8", "replace")
        parser = ArticleParser()
        parser.feed(raw)
        return "\n".join(parser.parts[:28])[:9500] if len(parser.parts) >= 4 else ""
    except (OSError, ValueError):
        return ""


def strip_feed_footer(text):
    return re.sub(r"\s*The post\s+.*$", "", str(text), flags=re.I).strip()


def compose(group, key):
    evidence = []
    for item in group:
        evidence.append(
            {
                "source": item["c"],
                "title": item["t"],
                "summary": strip_feed_footer(item["s"])[:450],
                "published": (item.get("published_at") or "")[:10],
                "article_reference": source_text(item["src"][0][1]),
            }
        )
    if not any(len(e["article_reference"]) >= 1200 for e in evidence):
        raise NoSource("not enough readable source text")
    return hp_ai.write_article(evidence, key)


def status(group):
    hosts = {(urlparse(x["src"][0][1]).hostname or "").removeprefix("www.") for x in group}
    official = any(o in h for h in hosts for o in OFFICIAL_HOSTS)
    return "Megerősített" if len(hosts) >= 2 or official else "Jelentett"


def read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prune(items, now):
    """Drop old RSS-born articles so the page's JSON stays small; catalog overrides are kept."""
    kept = []
    for x in items:
        if str(x.get("id", "")).startswith("rss-") and x.get("published_at"):
            try:
                age = now - dt.datetime.fromisoformat(x["published_at"])
            except ValueError:
                age = dt.timedelta(0)
            if age > dt.timedelta(days=KEEP_DAYS):
                continue
        kept.append(x)
    return kept


def main():
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("No ANTHROPIC_API_KEY: RSS collection continues without AI.")
        return
    now = dt.datetime.now(dt.timezone.utc)
    rows = read(NEWS, {"items": []}).get("items", [])
    archive = read(EDITORIAL, {"items": []})
    state = read(STATE, {"failed": {}})
    failed = state.setdefault("failed", {})
    done = {x["id"] for x in archive["items"]}
    limit = max(0, min(12, int(os.getenv("HIRPULT_AI_MAX_ARTICLES", "6"))))
    max_calls = int(os.getenv("HIRPULT_AI_MAX_CALLS", "16"))
    count, stop = 0, False

    # Cluster the same story across outlets first, then write the stories covered by the most outlets (same topic) first,
    # so the day's big story is not crowded out by single-source items. The sort is stable (newest first inside a tier).
    used, groups = set(), []
    for a in rows:
        if a["id"] in used or a["id"] in done or failed.get(a["id"], 0) >= MAX_TRIES:
            continue
        group = [a]
        used.add(a["id"])
        for b in rows:
            if b["id"] not in used and b["id"] not in done and b["c"] != a["c"] and similar(a, b):
                group.append(b)
                used.add(b["id"])
        groups.append(group)
    title_words = {x["id"]: words(x["t"]) for x in rows}

    def buzz(group):
        """How many other outlets run a headline on the same topic (two shared distinctive words)."""
        shared = set()
        for a in group:
            for b in rows:
                if b["c"] != a["c"] and len(title_words[a["id"]] & title_words[b["id"]]) >= 2:
                    shared.add(b["c"])
        return max(len({x["c"] for x in group}) - 1, len(shared))

    groups.sort(key=lambda g: -min(buzz(g), 4))

    for group in groups:
        if stop or count >= limit or hp_ai.USAGE["calls"] >= max_calls:
            break
        a = group[0]
        try:
            article = compose(group, key)
        except NoSource:
            failed[a["id"]] = MAX_TRIES  # paywalled or unreadable: do not try again
            continue
        except ValueError as exc:
            failed[a["id"]] = failed.get(a["id"], 0) + 1
            print("Article skipped:", a["id"], str(exc)[:200])
            continue
        except hp_ai.ApiError as exc:
            print("API error:", exc)
            if exc.status in (400, 401, 402, 403, 404):
                print("Stopping AI calls for this run: check the key, workspace id, billing and model access.")
                stop = True
            elif exc.status == 429:
                stop = True
            continue

        merged = dict(a)
        merged.update(
            t=article["title"][:180],
            s=article["lead"][:500],
            p=article["paragraphs"],
            c="Hírpult",
            st=status(group),
            cav=article["cav"] or ("Egyetlen forrás alapján készült összefoglaló, a részletek az eredeti cikkben ellenőrizhetők." if len(group) == 1 else ""),
            op=article["op"],
            ai_edited=True,
            src=[[x["c"], x["src"][0][1]] for x in group],
        )
        if article["section"]:
            merged["r"] = article["section"]
        if not merged.get("img"):
            donor = next((x for x in group if x.get("img")), None)
            if donor:
                merged.update({k: donor.get(k, "") for k in ("img", "imgs", "imgl", "cred")})
        archive["items"].append(merged)
        done.add(a["id"])
        failed.pop(a["id"], None)
        count += 1

    live_ids = {x["id"] for x in rows}
    state["failed"] = {k: v for k, v in failed.items() if k in live_ids}
    pruned = prune(archive["items"], now)
    if count or len(pruned) != len(archive["items"]):
        archive["items"] = pruned
        write(EDITORIAL, archive)
    write(STATE, state)
    cost = hp_ai.USAGE["input_tokens"] * 0.10 / 1e6 + hp_ai.USAGE["output_tokens"] * 0.50 / 1e6
    print(f"Articles written: {count}; API calls: {hp_ai.USAGE['calls']}; tokens in/out: "
          f"{hp_ai.USAGE['input_tokens']}/{hp_ai.USAGE['output_tokens']} (about ${cost:.3f} at Haiku 5.5 prices)")


if __name__ == "__main__":
    main()
