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
    def test_near_duplicate(self):
        r = "댓글 남겨주셔서 감사합니다 😊 오늘도 편안한 하루 보내세요."
        ok, why = m.quality_ok(r, m.DEFAULT_CONFIG, [r])
        self.assertFalse(ok)
        self.assertEqual(why, "near_duplicate")

if __name__ == '__main__':
    unittest.main()
