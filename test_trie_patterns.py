# -*- coding: utf-8 -*-
import json
import unittest
from datetime import datetime, timezone, timedelta

from trie.models import load_config
from trie.scout import normalize_record
from trie.patterns import freshness_weight, aggregate_patterns

NOW = datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)


def rec(ref, source="owned_official", observed="2026-10-05T23:00:00+00:00", interaction=0.8, click=None):
    return normalize_record({
        "source_type": source,
        "source_ref": ref,
        "observed_at": observed,
        "lane": "fortune_engagement",
        "features": {
            "topic": "재물운",
            "hook_type": "unexpected_prediction",
            "format": "text_image",
            "visual_pattern": "single_focus_card",
            "cta_type": "comment",
        },
        "signals": {"interaction_rate_score": interaction, "click_rate_score": click},
        "risk_flags": [],
    })


class TriePatternsTest(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()

    def test_freshness_buckets_are_exact(self):
        cases = [(7, 1.0), (8, 0.8), (30, 0.8), (31, 0.6), (90, 0.6), (91, 0.4), (180, 0.4), (181, 0.2)]
        for days, expected in cases:
            observed = (NOW - timedelta(days=days)).isoformat()
            self.assertEqual(freshness_weight(observed, NOW, self.cfg), expected)

    def test_naive_and_materially_future_timestamps_rejected(self):
        with self.assertRaises(ValueError):
            freshness_weight("2026-10-05T23:00:00", NOW, self.cfg)
        with self.assertRaises(ValueError):
            freshness_weight((NOW + timedelta(minutes=6)).isoformat(), NOW, self.cfg)

    def test_small_clock_skew_is_freshest(self):
        self.assertEqual(freshness_weight((NOW + timedelta(minutes=5)).isoformat(), NOW, self.cfg), 1.0)

    def test_aggregation_is_order_independent_and_deterministic(self):
        records = [rec("a", "owned_official", interaction=0.8), rec("b", "public_research", interaction=0.6)]
        a = [x.to_dict() for x in aggregate_patterns(records, now=NOW, config=self.cfg)]
        b = [x.to_dict() for x in aggregate_patterns(list(reversed(records)), now=NOW, config=self.cfg)]
        self.assertEqual(json.dumps(a, ensure_ascii=False, sort_keys=True), json.dumps(b, ensure_ascii=False, sort_keys=True))
        self.assertEqual(a[0]["sample_size"], 2)
        self.assertAlmostEqual(a[0]["source_trust_factor"], 0.8)
        self.assertAlmostEqual(a[0]["signals"]["interaction_rate_score"], 0.7)
        self.assertIsNone(a[0]["signals"]["click_rate_score"])

    def test_missing_signals_are_none_and_no_raw_creative_fields_exist(self):
        agg = aggregate_patterns([rec("a")], now=NOW, config=self.cfg)[0].to_dict()
        self.assertIsNone(agg["signals"].get("conversion_rate_score"))
        text = json.dumps(agg, ensure_ascii=False)
        for forbidden in ("full_text", "raw_post", "downloaded_video", "birth_date"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
