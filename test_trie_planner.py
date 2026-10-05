# -*- coding: utf-8 -*-
import json
import unittest
from datetime import datetime, timezone

from trie.models import RankedPattern, load_config
from trie.planner import is_eligible, plan_recommendations

NOW = datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)


def ranked(pid="TRIEPAT-A", sample=5, confidence=0.5, growth=0.8, revenue=None, flags=()):
    return RankedPattern(
        pattern_id=pid,
        lane="fortune_engagement",
        features={
            "topic": "재물운",
            "hook_type": "unexpected_prediction",
            "format": "text_image",
            "visual_pattern": "single_focus_card",
            "cta_type": "comment",
        },
        sample_size=sample,
        source_counts={"owned_official": sample},
        source_trust_factor=1.0,
        freshness_weight=1.0,
        signals={},
        risk_flags=tuple(flags),
        growth_score=growth,
        revenue_score=revenue,
        confidence=confidence,
    )


class TriePlannerTest(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()

    def test_eligibility_thresholds_and_blocking_flags(self):
        for item in [
            ranked(sample=2),
            ranked(confidence=0.24),
            ranked(growth=None, revenue=None),
            ranked(flags=("privacy",)),
        ]:
            ok, _ = is_eligible(item, self.cfg)
            self.assertFalse(ok)

    def test_empty_input_returns_empty(self):
        self.assertEqual(plan_recommendations([], generated_at=NOW, config=self.cfg), [])

    def test_recommendation_schema_is_advisory_only(self):
        rec = plan_recommendations([ranked()], generated_at=NOW, config=self.cfg)[0]
        data = rec.to_dict()
        self.assertEqual(data["schema"], "trie-recommendation-v1")
        self.assertEqual(data["lane"], "fortune_engagement")
        self.assertEqual(data["topic"], "재물운")
        self.assertEqual(data["hook_pattern"], "unexpected_prediction")
        self.assertEqual(data["format"], "text_image")
        self.assertEqual(data["visual_pattern"], "single_focus_card")
        self.assertEqual(data["cta"], "comment")
        self.assertTrue(data["canary"])
        self.assertEqual(data["source_policy"], "derived_patterns_only")
        self.assertIsNone(data["revenue_score"])
        text = json.dumps(data)
        for forbidden in ("approval_id", "signature", "receipt", "publish_command"):
            self.assertNotIn(forbidden, text)

    def test_objective_sort_is_deterministic(self):
        a = ranked("TRIEPAT-A", growth=0.5, revenue=0.9)
        b = ranked("TRIEPAT-B", growth=0.9, revenue=0.4)
        growth = plan_recommendations([a, b], generated_at=NOW, config=self.cfg, objective="growth")
        revenue = plan_recommendations([a, b], generated_at=NOW, config=self.cfg, objective="revenue")
        balanced = plan_recommendations([a, b], generated_at=NOW, config=self.cfg, objective="balanced")
        self.assertEqual(growth[0].pattern_id, "TRIEPAT-B")
        self.assertEqual(revenue[0].pattern_id, "TRIEPAT-A")
        self.assertEqual(balanced[0].pattern_id, "TRIEPAT-A")

    def test_invalid_objective_rejected(self):
        with self.assertRaises(ValueError):
            plan_recommendations([ranked()], generated_at=NOW, config=self.cfg, objective="magic")


if __name__ == "__main__":
    unittest.main()
