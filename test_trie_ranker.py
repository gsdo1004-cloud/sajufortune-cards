# -*- coding: utf-8 -*-
import unittest

from trie.models import PatternAggregate, load_config
from trie.ranker import weighted_available_mean, rank_pattern, rank_patterns


def pattern(pid="TRIEPAT-A", sample=5, freshness=0.8, trust=1.0, signals=None):
    base = {
        "interaction_rate_score": 0.8,
        "conversation_rate_score": 0.6,
        "amplification_rate_score": 0.4,
        "view_velocity_score": 1.0,
        "click_rate_score": 0.5,
        "conversion_rate_score": 0.4,
        "revenue_efficiency_score": 0.3,
    }
    if signals is not None:
        base.update(signals)
    return PatternAggregate(
        pattern_id=pid,
        lane="fortune_engagement",
        features={"topic": "재물운", "hook_type": "unexpected_prediction"},
        sample_size=sample,
        source_counts={"owned_official": sample},
        source_trust_factor=trust,
        freshness_weight=freshness,
        signals=base,
        risk_flags=(),
    )


class TrieRankerTest(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()

    def test_exact_growth_and_revenue_weights(self):
        ranked = rank_pattern(pattern(), self.cfg)
        expected_growth = 0.8*0.20 + 0.6*0.35 + 0.4*0.25 + 1.0*0.20
        expected_revenue = 0.5*0.30 + 0.4*0.45 + 0.3*0.25
        self.assertAlmostEqual(ranked.growth_score, expected_growth)
        self.assertAlmostEqual(ranked.revenue_score, expected_revenue)

    def test_missing_signal_renormalizes_weight(self):
        weights = {"a": 0.2, "b": 0.8}
        self.assertAlmostEqual(weighted_available_mean({"a": 1.0, "b": None}, weights), 1.0)

    def test_all_missing_family_is_none(self):
        ranked = rank_pattern(pattern(signals={
            "interaction_rate_score": None,
            "conversation_rate_score": None,
            "amplification_rate_score": None,
            "view_velocity_score": None,
            "click_rate_score": None,
            "conversion_rate_score": None,
            "revenue_efficiency_score": None,
        }), self.cfg)
        self.assertIsNone(ranked.growth_score)
        self.assertIsNone(ranked.revenue_score)

    def test_confidence_formula_and_cap(self):
        ranked = rank_pattern(pattern(sample=5, freshness=0.8, trust=0.6), self.cfg)
        self.assertAlmostEqual(ranked.confidence, 0.5 * 0.8 * 0.6)
        capped = rank_pattern(pattern(sample=50, freshness=1.0, trust=1.0), self.cfg)
        self.assertEqual(capped.confidence, 1.0)

    def test_rank_patterns_order_is_deterministic(self):
        out = rank_patterns([pattern("TRIEPAT-Z"), pattern("TRIEPAT-A")], self.cfg)
        self.assertEqual([x.pattern_id for x in out], ["TRIEPAT-A", "TRIEPAT-Z"])


if __name__ == "__main__":
    unittest.main()
