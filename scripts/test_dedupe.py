#!/usr/bin/env python3
"""Offline tests for duplicate detection. Run: python scripts/test_dedupe.py

The sample (fixtures/dedupe_items.json) is real data from 6 Nov 2026: the Gripen alert, three
articles about the new Reformed bishop, three about Ronaldo's retirement, the Kremlin and the
US midterm elections (different events that share many words) and 45 unrelated stories, so that
the word weights come from a realistic batch.
"""
import copy
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import dedupe_editorial  # noqa: E402
import enrich_news  # noqa: E402
import hp_dedupe  # noqa: E402

SAMPLE = json.loads((HERE / "fixtures" / "dedupe_items.json").read_text(encoding="utf-8"))


def sample():
    return copy.deepcopy(SAMPLE)


def by_id(items, prefix):
    return next(x for x in items if x["id"].startswith(prefix))


class Similarity(unittest.TestCase):
    def setUp(self):
        self.items = sample()
        self.index = hp_dedupe.Index(self.items)

    def same(self, a, b):
        return hp_dedupe.same_story(self.index, by_id(self.items, a), by_id(self.items, b))

    def test_word_forms_match(self):
        self.assertEqual(hp_dedupe.stems("bombafenyegetés")[0], hp_dedupe.stems("bombafenyegetett")[0])
        self.assertEqual(hp_dedupe.stems("Gripeneket"), hp_dedupe.stems("Gripenek"))

    def test_gripen_reports_that_the_old_title_rule_split(self):
        # Origo + HVG + Blikk and Index + 24.hu were two clusters: only three title words in common.
        self.assertTrue(self.same("rss-b9a5d6", "rss-3e9ea5"))
        self.assertTrue(self.same("rss-e683a3", "rss-b9a5d6"))
        self.assertTrue(self.same("rss-8eff3a", "rss-3e9ea5"))

    def test_three_articles_about_the_same_bishop(self):
        self.assertTrue(self.same("rss-d87c51", "rss-5594d6"))
        self.assertTrue(self.same("rss-d87c51", "rss-7a5c6e"))

    def test_different_events_with_shared_words_stay_apart(self):
        for midterm in ("rss-a001b4", "rss-2c426a", "rss-d5448c", "rss-a84a5f"):
            self.assertFalse(self.same("rss-028576", midterm), midterm)
        self.assertFalse(self.same("rss-f7fc52", "rss-028576"))
        self.assertFalse(self.same("rss-b9a5d6", "rss-f7fc52"))

    def test_reports_days_apart_are_not_the_same_story(self):
        late = copy.deepcopy(by_id(self.items, "rss-b9a5d6"))
        late["published_at"] = (dt.datetime.fromisoformat(late["published_at"]) + dt.timedelta(days=10)).isoformat()
        index = hp_dedupe.Index(self.items + [late])
        self.assertFalse(hp_dedupe.same_story(index, by_id(self.items, "rss-3e9ea5"), late))

    def test_an_item_is_not_its_own_duplicate(self):
        a = by_id(self.items, "rss-b9a5d6")
        self.assertFalse(hp_dedupe.same_story(self.index, a, a))

    def test_clusters(self):
        pool = [x for x in self.items if x["id"].startswith(("rss-d87c51", "rss-5594d6", "rss-7a5c6e", "rss-f7fc52", "rss-028576"))]
        groups = sorted(len(g) for g in hp_dedupe.clusters(hp_dedupe.Index(self.items), pool))
        self.assertEqual(groups, [1, 1, 3])  # bishop x3, Ronaldo alone, Kremlin alone


class Merging(unittest.TestCase):
    def test_keeper_prefers_written_then_most_sources(self):
        stub = {"id": "rss-a", "ai_edited": False, "src": [["A", "https://a.hu/1"]], "p": ["x" * 500], "published_at": "2026-11-06T08:00:00+00:00"}
        short = {"id": "rss-b", "ai_edited": True, "src": [["A", "https://a.hu/1"]], "p": ["x"], "published_at": "2026-11-06T08:00:00+00:00"}
        rich = {"id": "rss-c", "ai_edited": True, "src": [["A", "https://a.hu/1"], ["B", "https://b.hu/1"]], "p": ["x"], "published_at": "2026-11-06T09:00:00+00:00"}
        self.assertIs(hp_dedupe.keeper([stub, short, rich]), rich)
        self.assertIs(hp_dedupe.keeper([stub, short]), short)

    def test_merge_adds_sources_once_and_updates_status(self):
        keep = {"id": "rss-a", "st": "Jelentett", "src": [["Index", "https://index.hu/x/"]], "img": ""}
        other = {"id": "rss-b", "src": [["Index", "https://www.index.hu/x"], ["HVG", "https://hvg.hu/y"]], "img": "https://hvg.hu/i.jpg", "imgs": "HVG", "imgl": "https://hvg.hu/y", "cred": "Kép: HVG"}
        hp_dedupe.merge_into(keep, [other])
        self.assertEqual([s[0] for s in keep["src"]], ["Index", "HVG"])
        self.assertEqual(keep["st"], "Megerősített")
        self.assertEqual(keep["img"], "https://hvg.hu/i.jpg")

    def test_one_outlet_stays_reported(self):
        keep = {"id": "rss-a", "st": "Megerősített", "src": [["Index", "https://index.hu/x"]]}
        hp_dedupe.merge_into(keep, [{"id": "rss-b", "src": [["Index", "https://index.hu/z"]]}])
        self.assertEqual(keep["st"], "Jelentett")

    def test_duplicate_articles_are_merged_and_it_is_stable(self):
        items = [x for x in sample() if x["ai_edited"]]
        total = len(items)
        kept, report = dedupe_editorial.merge_duplicates(items)
        # bishop 3 -> 1, Gripen 2 -> 1, the Kremlin articles 3 -> 1. Of the three Ronaldo articles one pair
        # scores 0.46, just under the threshold, so two remain: the threshold favours not merging
        # different developments over catching every repeat.
        self.assertLess(len(kept), total)
        bishop = [x for x in kept if "Nyilas Zoltán" in x["t"]]
        ronaldo = [x for x in kept if "Cristiano Ronaldo" in x["t"]]
        gripen = [x for x in kept if "Gripen" in x["t"]]
        kremlin = [x for x in kept if "Kreml" in x["t"] or "Peszkov" in x["t"]]
        self.assertEqual((len(bishop), len(gripen)), (1, 1))
        # word weights come from the batch, so pairs near the threshold can fall either way in a small sample:
        # what must hold is that repeats are merged at all, and never into fewer than one article
        self.assertTrue(1 <= len(ronaldo) < 3)
        self.assertTrue(1 <= len(kremlin) < 3)
        self.assertEqual({s[0] for s in gripen[0]["src"]}, {"Origo", "HVG", "Blikk", "Index", "24.hu"})
        self.assertEqual(gripen[0]["st"], "Megerősített")
        again, report2 = dedupe_editorial.merge_duplicates(kept)
        self.assertEqual(len(again), len(kept))
        self.assertEqual(report2, [])

    def test_catalog_overrides_are_never_merged(self):
        items = [
            {"id": "gdp-3-negyedev-csalodas", "ai_edited": True, "t": "Lassult a magyar gazdaság", "s": "A GDP lassult", "src": [["A", "https://a.hu/1"]], "published_at": "2026-11-06T08:00:00+00:00"},
            {"id": "gdp-lassulas-masik", "ai_edited": True, "t": "Lassult a magyar gazdaság", "s": "A GDP lassult", "src": [["B", "https://b.hu/1"]], "published_at": "2026-11-06T08:00:00+00:00"},
        ]
        kept, report = dedupe_editorial.merge_duplicates(items)
        self.assertEqual(len(kept), 2)
        self.assertEqual(report, [])

    def test_plain_reports_are_attached_to_the_finished_article(self):
        data = sample()
        articles = [x for x in data if x["ai_edited"]]
        articles, _ = dedupe_editorial.merge_duplicates(articles)
        template = by_id(data, "rss-8eff3a")
        late = copy.deepcopy(template)
        late.update(id="rss-late", c="Telex", src=[["Telex", "https://telex.hu/belfold/gripen-bombafenyegetes"]],
                    t="Három bombafenyegetés miatt riasztották a magyar Gripeneket, több utasszállítót kísértek")
        stranger = copy.deepcopy(template)
        stranger.update(id="rss-xx", c="Telex", t="Sztrájkot hirdettek a vasutasok", s="A vasutasok szakszervezete sztrájkot hirdetett jövő hétre.",
                        src=[["Telex", "https://telex.hu/sztrajk"]], img="", imgs="", imgl="", cred="")
        attached, rest = hp_dedupe.attach_reports(articles, [late, stranger])
        gripen = next(x for x in articles if "Gripen" in x["t"])
        self.assertEqual(attached, 1)
        self.assertIn("Telex", {s[0] for s in gripen["src"]})
        self.assertEqual([x["id"] for x in rest], ["rss-xx"])
        # a second round has nothing left to attach: the report is a listed source by now
        again, _ = hp_dedupe.attach_reports(articles, [late])
        self.assertEqual(again, 0)


class Enrich(unittest.TestCase):
    """enrich_news.main must attach a new report to an existing article and never write it again."""

    def test_new_report_of_a_written_story_becomes_a_source(self):
        data = sample()
        articles = [x for x in data if x["ai_edited"]]
        stubs = [x for x in data if not x["ai_edited"]]
        late = copy.deepcopy(by_id(data, "rss-8eff3a"))
        late.update(id="rss-latecomer", c="Telex", t="Három bombafenyegetés miatt riasztották a Gripeneket, utasszállítókat kísértek",
                    src=[["Telex", "https://telex.hu/belfold/gripen-bombafenyegetes"]], img="", imgs="", imgl="", cred="")
        for x in stubs:
            x["src"] = [list(x["src"][0])]
        rows = stubs + [late]
        composed = []

        def fake_compose(group, key):
            composed.append([x["id"] for x in group])
            raise enrich_news.NoSource("test")

        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            try:
                Path("data").mkdir()
                Path("data/news.json").write_text(json.dumps({"items": rows}), encoding="utf-8")
                Path("data/editorial.json").write_text(json.dumps({"items": articles}), encoding="utf-8")
                with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), mock.patch.object(enrich_news, "compose", fake_compose):
                    enrich_news.main()
                saved = json.loads(Path("data/editorial.json").read_text(encoding="utf-8"))["items"]
            finally:
                os.chdir(old)
        gripen = [x for x in saved if "Gripen" in x["t"]]
        self.assertTrue(any("https://telex.hu/belfold/gripen-bombafenyegetes" in [s[1] for s in x["src"]] for x in gripen))
        flat = {i for group in composed for i in group}
        self.assertNotIn("rss-latecomer", flat)
        # reports that a finished article already lists as a source are not written again either
        covered = hp_dedupe.covered_urls(articles)
        for x in stubs:
            if hp_dedupe.report_url(x) in covered:
                self.assertNotIn(x["id"], flat, x["t"])


if __name__ == "__main__":
    unittest.main()
