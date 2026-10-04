# -*- coding: utf-8 -*-
import unittest

from threads_fortune_public import has_private_birth_data, zodiac_slug, public_reply


class ThreadsFortunePublicTest(unittest.TestCase):
    def test_zodiac_from_explicit_sign(self):
        self.assertEqual(zodiac_slug("개띠 재물운"), "dog")
        self.assertEqual(zodiac_slug("범띠 이직운"), "tiger")

    def test_zodiac_from_year(self):
        self.assertEqual(zodiac_slug("1982년 사업운"), "dog")
        self.assertEqual(zodiac_slug("1994 재물운"), "dog")

    def test_private_birth_data_detection(self):
        self.assertTrue(has_private_birth_data("1994.05.24 오전 03:31 남"))
        self.assertTrue(has_private_birth_data("생년월일 1982-02-09 출생시간 12:10"))
        self.assertFalse(has_private_birth_data("1982년 개띠 재물운"))

    def test_public_reply_never_echoes_birth_date(self):
        src = "1994.05.24 오전 03:31 남자 재물운"
        out = public_reply(src, "2026-10-04")
        self.assertTrue(out)
        self.assertNotIn("1994.05.24", out)
        self.assertNotIn("03:31", out)
        self.assertIn("DM", out)

    def test_public_zodiac_reply(self):
        out = public_reply("1982년 개띠 재물운 궁금해요", "2026-10-04")
        self.assertTrue(out)
        self.assertIn("개띠", out)
        self.assertIn("재물", out)
        self.assertIn("DM", out)
        self.assertLessEqual(len(out), 120)


if __name__ == "__main__":
    unittest.main()
