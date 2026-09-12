# -*- coding: utf-8 -*-
import datetime as dt
import unittest

import threads_growth as g


class GrowthSafetyTests(unittest.TestCase):
    def setUp(self):
        self.cfg = g.load_config()
        self.state = g.default_state()

    def test_quality_rejects_promo_and_urls(self):
        for text in [
            "자세한 내용은 https://example.com 에서 보세요",
            "제 프로필 링크에서 무료운세 보세요",
            "@someone 정말 좋은 해석이네요",
            "#사주 좋은 글 감사합니다",
        ]:
            ok, _ = g.quality_gate(text, self.cfg, self.state, external=True)
            self.assertFalse(ok, text)

    def test_quality_accepts_specific_nonpromo_reply(self):
        text = "같은 재성이라도 월령과 강약을 같이 보면 해석이 조금 달라질 수 있겠네요."
        ok, reason = g.quality_gate(text, self.cfg, self.state, external=True)
        self.assertTrue(ok, reason)

    def test_duplicate_rejected(self):
        text = "대운만 보기보다 세운의 충합까지 같이 보면 시점이 더 선명해지더군요."
        self.state["sent"].append({"text_hash": g.text_hash(text)})
        ok, reason = g.quality_gate(text, self.cfg, self.state, external=True)
        self.assertFalse(ok)
        self.assertEqual(reason, "duplicate")

    def test_daily_external_cap(self):
        b = g.today_bucket(self.state, dt.datetime.now(dt.timezone.utc))
        b["external"] = self.cfg["external_daily_cap"]
        self.assertFalse(g.can_send_external(self.cfg, self.state, "saju.pharmacy"))

    def test_per_target_cap(self):
        b = g.today_bucket(self.state)
        b["per_target"]["saju.pharmacy"] = 1
        self.assertFalse(g.can_send_external(self.cfg, self.state, "saju.pharmacy"))


    def test_near_duplicate_rejected(self):
        old = "대운만 보기보다 세운의 충합까지 함께 보면 시점이 더 선명해집니다."
        self.state["sent"].append({"text_hash": g.text_hash(old), "text": old})
        new = "대운만 보기보다 세운의 충합까지 같이 보면 시점이 더 선명해집니다."
        ok, reason = g.quality_gate(new, self.cfg, self.state, external=True)
        self.assertFalse(ok)
        self.assertEqual(reason, "near_duplicate")

    def test_relevance(self):
        self.assertGreater(g.relevant_score("오늘은 정재와 재물운을 같이 봅니다", self.cfg), 0)
        self.assertEqual(g.relevant_score("야구 경기 결과", self.cfg), 0)


if __name__ == "__main__":
    unittest.main()
