# -*- coding: utf-8 -*-
import math
import tempfile
import unittest
from pathlib import Path

from trie.io import atomic_write_json, read_json
from trie.models import SOURCE_TRUST, deterministic_id, load_config, validate_unit_interval


class TrieModelsTest(unittest.TestCase):
    def test_unit_interval_accepts_valid_and_none(self):
        for value in (0.0, 0.5, 1.0, None):
            self.assertEqual(validate_unit_interval(value, "score"), value)

    def test_unit_interval_rejects_invalid_numbers(self):
        for value in (-0.01, 1.01, math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                validate_unit_interval(value, "score")

    def test_source_trust_and_config_are_exact(self):
        self.assertEqual(SOURCE_TRUST, {"owned_official": 1.0, "internal_attribution": 0.8, "public_research": 0.6})
        cfg = load_config()
        self.assertEqual(cfg["growth_weights"], {"interaction_rate_score": 0.20, "conversation_rate_score": 0.35, "amplification_rate_score": 0.25, "view_velocity_score": 0.20})
        self.assertEqual(cfg["revenue_weights"], {"click_rate_score": 0.30, "conversion_rate_score": 0.45, "revenue_efficiency_score": 0.25})
        self.assertEqual(cfg["min_sample_size"], 3)
        self.assertEqual(cfg["min_confidence"], 0.25)

    def test_deterministic_id_is_stable(self):
        a = deterministic_id("TRIEPAT", ["a", "b"])
        b = deterministic_id("TRIEPAT", ["a", "b"])
        c = deterministic_id("TRIEPAT", ["a", "c"])
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(a.startswith("TRIEPAT-"))

    def test_atomic_json_roundtrip_preserves_korean(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            atomic_write_json(p, {"topic": "재물운"})
            self.assertEqual(read_json(p), {"topic": "재물운"})

    def test_atomic_write_failure_keeps_existing_destination(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text('{"old": true}\n', encoding="utf-8")
            before = p.read_bytes()
            with self.assertRaises((TypeError, ValueError)):
                atomic_write_json(p, {"bad": object()})
            self.assertEqual(p.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
