#!/usr/bin/env python3
"""Offline tests for the article checks and the API client. Run: python scripts/test_hp_ai.py"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
import hp_ai  # noqa: E402

SOURCE = (
    "A Magyar Nemzeti Bank Monetáris Tanácsa október 20-án ülésezett, és az alapkamatot 5,5 százalékon hagyta, "
    "az éjszakai betéti kamat 4,5, az éjszakai hitelkamat pedig 6,5 százalék maradt. A szeptemberi infláció 1,6 "
    "százalék volt. Varga Mihály szerint az óvatos monetáris politika a nemzetközi helyzet miatt indokolt, és "
    "az eurócsatlakozás tartósan fegyelmezett költségvetést igényel. A kormány hiánycéljai 2028-ban 4, 2029-ben 3,4, "
    "2030-ban pedig 2,8 százalék, a részletek még nem ismertek. Szerinte „nem egyetlen év eredménye” számít."
)
GOOD = {
    "title": "Marad az 5,5 százalékos alapkamat",
    "lead": "A Monetáris Tanács nem változtatott a kamaton, a szeptemberi infláció 1,6 százalék volt.",
    "paragraphs": [
        "Változatlan maradt a jegybanki alapkamat: a testület október 20-i ülésén 5,5 százalékos szinten tartotta, "
        "az éjszakai betét 4,5, az éjszakai hitel 6,5 százalékos kamattal él tovább.",
        "Az árak emelkedése szeptemberben 1,6 százalékot ért el. A bankelnök szerint a világgazdasági bizonytalanság "
        "miatt a körültekintő kamatpolitika indokolt, az euró bevezetése hosszabb távú költségvetési fegyelmet kíván.",
        "A kormány hiánycéljai 2028-ra 4, 2029-re 3,4, 2030-ra 2,8 százalékot tesznek ki, a részletek még hiányoznak.",
    ],
    "section": "Gazdaság",
    "cav": "A cikk a jegybankelnök szavaira támaszkodik, a hiánycélok részletei nem ismertek.",
    "op": "A változatlan kamat nem meglepetés, de a hiánycélok körüli homály aggasztó: kiszámítható költségvetési "
    "pálya nélkül az eurócsatlakozás ígérete üres szó marad.",
}


def check(article, target=100):
    return hp_ai.problems(article, SOURCE, SOURCE, target)


class Checks(unittest.TestCase):
    def test_good_article_passes(self):
        self.assertEqual(check(GOOD), [])

    def test_invented_number_is_flagged(self):
        bad = dict(GOOD, op=GOOD["op"] + " A hiány akár 7,9 százalék is lehet.")
        self.assertTrue(any("7,9" in p for p in check(bad)))

    def test_number_formats_match(self):
        self.assertEqual(hp_ai.numbers("1 250 milliárd, 1.250 és 5.5"), {"1250", "5,5"})

    def test_unverified_quote_is_flagged(self):
        bad = dict(GOOD, op=GOOD["op"] + " Az elnök „soha nem látott kamatvágást ígért”.")
        self.assertTrue(any("quotation" in p for p in check(bad)))

    def test_verbatim_short_quote_is_allowed(self):
        ok = dict(GOOD, op=GOOD["op"] + " Az elnök szerint „nem egyetlen év eredménye” számít.")
        self.assertEqual(check(ok), [])

    def test_word_for_word_copy_is_flagged(self):
        copied = dict(GOOD, paragraphs=[SOURCE.replace("„", "").replace("”", "")])
        self.assertTrue(any("word for word" in p for p in check(copied)))

    def test_markup_and_ai_mentions_are_flagged(self):
        self.assertTrue(check(dict(GOOD, title="<b>Marad</b> az alapkamat")))
        self.assertTrue(check(dict(GOOD, op=GOOD["op"] + " Ezt a mesterséges intelligencia írta.")))

    def test_missing_op_is_flagged(self):
        self.assertTrue(check(dict(GOOD, op="")))

    def test_length_follows_target(self):
        self.assertTrue(any("words" in p for p in check(GOOD, target=400)))


class SpelledNumbers(unittest.TestCase):
    def test_values(self):
        v = hp_ai.spelled_value
        self.assertEqual([v("három"), v("huszonöt"), v("harmincöt"), v("tizenhárom"), v("milliárd"), v("hármat")],
                         [3, 25, 35, 13, 10**9, 3])
        for word in ("egy", "hét", "ötlet", "negyedik", "tizenegy"[:5], "alapkamat"):
            self.assertIsNone(v(word), word)

    def test_invented_spelled_number_is_flagged(self):
        bad = dict(GOOD, op=GOOD["op"] + " Legalább tizenkét ember bukhat meg ezen.")
        self.assertTrue(any("number" in p and "tizenkét" in p for p in check(bad)))

    def test_spelled_number_matching_digits_is_allowed(self):
        ok = dict(GOOD, op=GOOD["op"] + " A kamat öt és fél százalék maradt.")
        self.assertEqual(check(ok), [])

    def test_unmatched_spelled_number_with_other_digit_is_flagged(self):
        bad = dict(GOOD, op=GOOD["op"] + " Kilenc évig így marad.")
        self.assertTrue(any("kilenc" in p for p in check(bad)))


class JsonRepair(unittest.TestCase):
    def test_bad_json_gets_a_repair_round(self):
        evidence = [{"title": "t", "summary": SOURCE, "published": "", "article_reference": SOURCE}]
        good = json.dumps(dict(GOOD), ensure_ascii=False)
        replies = iter(['{"title": "rossz "idézet"", "lead": "x"}', good])
        seen = []

        def fake_ask(system, messages, key, max_tokens=8000):
            seen.append(len(messages))
            return next(replies)

        with mock.patch.object(hp_ai, "ask", fake_ask), mock.patch.object(hp_ai, "target_words", lambda t: 100):
            article = hp_ai.write_article(evidence, "k")
        self.assertEqual(seen, [1, 3])
        self.assertEqual(article["title"], GOOD["title"])


class Client(unittest.TestCase):
    def reply(self, blocks, stop="end_turn"):
        return {"content": blocks, "stop_reason": stop, "usage": {"input_tokens": 10, "output_tokens": 5}}

    def test_thinking_block_is_skipped_and_no_sampling_params(self):
        sent = []

        def fake_post(body, key, scheme):
            sent.append((body, scheme))
            return self.reply([{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "{\"a\": 1}"}])

        with mock.patch.object(hp_ai, "_post", fake_post):
            text = hp_ai.ask("sys", [{"role": "user", "content": "hi"}], "k")
        self.assertEqual(json.loads(text), {"a": 1})
        body = sent[0][0]
        for forbidden in ("temperature", "top_p", "top_k"):
            self.assertNotIn(forbidden, body)
        self.assertEqual(body["messages"][-1]["role"], "user")

    def test_falls_back_to_bearer_after_401(self):
        schemes = []

        def fake_post(body, key, scheme):
            schemes.append(scheme)
            if scheme == "x-api-key":
                raise hp_ai.ApiError(401, "authentication_error")
            return self.reply([{"type": "text", "text": "{}"}])

        with mock.patch.object(hp_ai, "_post", fake_post):
            hp_ai.ask("sys", [{"role": "user", "content": "hi"}], "k")
        self.assertEqual(schemes, ["x-api-key", "bearer"])

    def test_low_effort_is_sent_by_default(self):
        sent = []
        hp_ai.SETTINGS["effort"] = "low"

        def fake_post(body, key, scheme):
            sent.append(dict(body))
            return self.reply([{"type": "text", "text": "{}"}])

        with mock.patch.object(hp_ai, "_post", fake_post):
            hp_ai.ask("sys", [{"role": "user", "content": "hi"}], "k")
        self.assertEqual(sent[0]["output_config"], {"effort": "low"})

    def test_rejected_effort_is_dropped_and_not_sent_again(self):
        sent = []
        hp_ai.SETTINGS["effort"] = "low"

        def fake_post(body, key, scheme):
            sent.append("output_config" in body)
            if "output_config" in body:
                raise hp_ai.ApiError(400, "invalid_request_error: output_config: Extra inputs are not permitted")
            return self.reply([{"type": "text", "text": "{}"}])

        try:
            with mock.patch.object(hp_ai, "_post", fake_post):
                hp_ai.ask("sys", [{"role": "user", "content": "hi"}], "k")
                hp_ai.ask("sys", [{"role": "user", "content": "again"}], "k")
        finally:
            hp_ai.SETTINGS["effort"] = "low"
        self.assertEqual(sent, [True, False, False])

    def test_other_400_errors_still_fail(self):
        hp_ai.SETTINGS["effort"] = "low"
        with mock.patch.object(hp_ai, "_post", mock.Mock(side_effect=hp_ai.ApiError(400, "invalid_request_error: bad model"))):
            with self.assertRaises(hp_ai.ApiError):
                hp_ai.ask("sys", [{"role": "user", "content": "hi"}], "k")

    def test_refusal_is_a_value_error(self):
        with mock.patch.object(hp_ai, "_post", lambda *a: self.reply([], stop="refusal")):
            with self.assertRaises(ValueError):
                hp_ai.ask("sys", [{"role": "user", "content": "hi"}], "k")

    def test_unescaped_quotes_are_salvaged(self):
        bad = ('{"title": "Cím", "lead": "Azt mondta, "nem megyünk"; kész.", "paragraphs": ["Első, "idézet" itt, hosszabb szöveg.", '
               '"Második bekezdés rendes szöveggel."], "section": "Külföld", "cav": "", "op": "Vélemény."}')
        article = hp_ai.parse_json(bad)
        self.assertEqual(article["lead"], "Azt mondta, „nem megyünk”; kész.")
        self.assertEqual(len(article["paragraphs"]), 2)
        self.assertEqual(article["section"], "Külföld")

    def test_parse_json_ignores_fences(self):
        self.assertEqual(hp_ai.parse_json("```json\n{\"x\": 2}\n```"), {"x": 2})


if __name__ == "__main__":
    unittest.main(verbosity=2)
