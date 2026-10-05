# -*- coding: utf-8 -*-
import unittest

from trie.feedback import normalize_feedback, attach_feedback
from trie.models import Recommendation


def recommendation(rid="TRIE-ABC"):
    return Recommendation(
        schema="trie-recommendation-v1",
        recommendation_id=rid,
        generated_at="2026-10-06T00:00:00+00:00",
        pattern_id="TRIEPAT-A",
        lane="fortune_engagement",
        topic="재물운",
        hook_pattern="unexpected_prediction",
        format="text_image",
        visual_pattern="single_focus_card",
        cta="comment",
        growth_score=0.8,
        revenue_score=None,
        confidence=0.5,
        sample_size=5,
    )


class TrieFeedbackTest(unittest.TestCase):
    def test_missing_metrics_stay_unknown_but_explicit_zero_is_real(self):
        missing = normalize_feedback({
            "recommendation_id": "TRIE-ABC",
            "status": "metrics_incomplete",
            "observed_at": "2026-10-06T01:00:00+00:00",
        })
        zero = normalize_feedback({
            "recommendation_id": "TRIE-ABC",
            "status": "complete",
            "observed_at": "2026-10-06T02:00:00+00:00",
            "views": 0,
            "revenue": 0,
        })
        self.assertIsNone(missing.views)
        self.assertIsNone(missing.revenue)
        self.assertEqual(zero.views, 0)
        self.assertEqual(zero.revenue, 0.0)

    def test_invalid_status_and_negative_metrics_rejected(self):
        with self.assertRaises(ValueError):
            normalize_feedback({"recommendation_id":"TRIE-ABC","status":"magic","observed_at":"x"})
        for field in ("views", "clicks", "conversions", "revenue"):
            raw = {"recommendation_id":"TRIE-ABC","status":"complete","observed_at":"2026-10-06T00:00:00+00:00", field: -1}
            with self.assertRaises(ValueError, msg=field):
                normalize_feedback(raw)

    def test_nonfinite_revenue_is_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                normalize_feedback({
                    "recommendation_id":"TRIE-ABC",
                    "status":"complete",
                    "observed_at":"2026-10-06T00:00:00+00:00",
                    "revenue":value,
                })

    def test_feedback_attaches_only_to_existing_recommendation(self):
        fb = normalize_feedback({
            "recommendation_id":"TRIE-ABC","status":"complete","observed_at":"2026-10-06T01:00:00+00:00","views":10
        })
        out = attach_feedback([recommendation()], [fb])
        self.assertEqual(out[0]["feedback"][0]["views"], 10)
        with self.assertRaises(ValueError):
            attach_feedback([recommendation()], [normalize_feedback({
                "recommendation_id":"TRIE-UNKNOWN","status":"rejected","observed_at":"2026-10-06T01:00:00+00:00"
            })])

    def test_rejected_feedback_has_error_without_fake_metrics_or_publish_fields(self):
        fb = normalize_feedback({
            "recommendation_id":"TRIE-ABC","status":"rejected","observed_at":"2026-10-06T01:00:00+00:00","error_code":"POLICY"
        })
        out = attach_feedback([recommendation()], [fb])[0]
        item = out["feedback"][0]
        self.assertEqual(item["error_code"], "POLICY")
        self.assertIsNone(item["views"])
        for forbidden in ("publish_command", "approval", "receipt", "url_call"):
            self.assertNotIn(forbidden, out)
            self.assertNotIn(forbidden, item)


if __name__ == "__main__":
    unittest.main()
