# -*- coding: utf-8 -*-
import unittest

from trie.scout import normalize_record, normalize_records


def raw(source_type="owned_official"):
    return {
        "source_type": source_type,
        "source_ref": "post:123",
        "observed_at": "2026-10-05T20:00:00+09:00",
        "lane": "fortune_engagement",
        "features": {
            "topic": "재물운",
            "hook_type": "unexpected_prediction",
            "format": "text_image",
            "visual_pattern": "single_focus_card",
            "cta_type": "comment",
            "unknown_feature": "drop-me",
        },
        "signals": {
            "interaction_rate_score": 0.8,
            "conversation_rate_score": 0.7,
            "click_rate_score": None,
        },
        "risk_flags": [],
    }


class TrieScoutTest(unittest.TestCase):
    def test_allowed_sources_preserve_provenance_and_trust(self):
        expected = {"owned_official": 1.0, "internal_attribution": 0.8, "public_research": 0.6}
        for source_type, trust in expected.items():
            rec = normalize_record(raw(source_type))
            self.assertEqual(rec.source_type, source_type)
            self.assertEqual(rec.source_ref, "post:123")
            self.assertEqual(rec.source_trust, trust)

    def test_unsupported_source_rejected(self):
        with self.assertRaises(ValueError):
            normalize_record(raw("browser_scrape"))

    def test_features_are_whitelisted(self):
        rec = normalize_record(raw())
        self.assertIn("topic", rec.features)
        self.assertNotIn("unknown_feature", rec.features)

    def test_forbidden_key_at_any_depth_rejected(self):
        for key, value in [
            ("birth_date", "1982-02-09"),
            ("full_text", "creator full post"),
            ("downloaded_video", "blob"),
            ("access_token", "secret"),
        ]:
            obj = raw()
            obj["features"]["nested"] = {"deeper": {key: value}}
            with self.assertRaises(ValueError, msg=key):
                normalize_record(obj)

    def test_signal_range_is_validated(self):
        obj = raw()
        obj["signals"]["interaction_rate_score"] = 1.5
        with self.assertRaises(ValueError):
            normalize_record(obj)

    def test_unknown_signal_is_ignored_but_known_none_preserved(self):
        obj = raw()
        obj["signals"]["mystery"] = 0.9
        rec = normalize_record(obj)
        self.assertNotIn("mystery", rec.signals)
        self.assertIsNone(rec.signals["click_rate_score"])

    def test_batch_normalizes_all(self):
        out = normalize_records([raw("owned_official"), raw("public_research")])
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
