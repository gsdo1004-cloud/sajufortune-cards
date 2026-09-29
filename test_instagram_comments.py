import unittest
import instagram_comments as m

class InstagramCommentSafetyTests(unittest.TestCase):
    def test_no_sales_links(self):
        ok, why = m.quality_ok("프로필 링크에서 구매하세요 https://x", m.DEFAULT_CONFIG, [])
        self.assertFalse(ok)
    def test_normal_question_reply(self):
        r = m.safe_reply("직장운이 궁금해요?", "user")
        ok, _ = m.quality_ok(r, m.DEFAULT_CONFIG, [])
        self.assertTrue(ok)
        self.assertNotIn("http", r)
    def test_media_context_shapes_reply(self):
        r = m.safe_reply("저도 궁금해요", "user", "2027 재물운이 좋아지는 띠")
        self.assertIn("재물운", r)
    def test_homepage_domain_allowed(self):
        c = {**m.DEFAULT_CONFIG, "blocked_terms": ["http://", "https://", "구매", "결제"]}
        ok, _ = m.quality_ok("더 자세한 개인 운세가 궁금하시면 sajufortune.kr의 무료 운세도 참고해보세요 🔮", c, [])
        self.assertTrue(ok)

    def test_near_duplicate(self):
        r = "댓글 남겨주셔서 감사합니다 😊 오늘도 편안한 하루 보내세요."
        ok, why = m.quality_ok(r, m.DEFAULT_CONFIG, [r])
        self.assertFalse(ok)
        self.assertEqual(why, "near_duplicate")

    def test_fortune_trigger_shadow(self):
        c={**m.DEFAULT_CONFIG,"fortune_trigger_terms":["사주","재물","직장"]}
        self.assertEqual(m.fortune_trigger("재물 궁금해요",c),"재물")
        self.assertIsNone(m.fortune_trigger("감사합니다",c))

    def test_fortune_shadow_does_not_store_raw_text_or_username(self):
        rec=m.fortune_shadow_record({
            "comment_id":"1","media_id":"2","username":"private_user",
            "text":"양력 1990-03-12 14:00 여 재물운","timestamp":"2026-09-30T00:00:00Z"
        },"재물")
        self.assertNotIn("text",rec)
        self.assertNotIn("username",rec)
        self.assertIn("text_hash",rec)

if __name__ == '__main__':
    unittest.main()
