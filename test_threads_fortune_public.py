# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from threads_fortune_public import has_birth_detail, parse_birth_input, zodiac_slug, public_reply


class ThreadsFortunePublicTest(unittest.TestCase):
    def test_zodiac_from_explicit_sign(self):
        self.assertEqual(zodiac_slug("개띠 재물운"), "dog")
        self.assertEqual(zodiac_slug("범띠 이직운"), "tiger")

    def test_zodiac_from_year(self):
        self.assertEqual(zodiac_slug("1982년 사업운"), "dog")
        self.assertEqual(zodiac_slug("1994 재물운"), "dog")

    def test_birth_detail_detection(self):
        self.assertTrue(has_birth_detail("1994.05.24 오전 03:31 남"))
        self.assertTrue(has_birth_detail("생년월일 1982-02-09 출생시간 12:10"))
        self.assertFalse(has_birth_detail("1982년 개띠 재물운"))

    def test_parse_birth_input(self):
        x = parse_birth_input("음력 1982.02.09 오후 12시10분 여자 재물운")
        self.assertEqual(x["birth_date"], "1982-02-09")
        self.assertEqual(x["birth_time"], "12:10")
        self.assertEqual(x["cal"], "lunar")
        self.assertEqual(x["gender"], "F")
        self.assertTrue(x["time_known"])

    def test_parse_two_digit_birth_year(self):
        x = parse_birth_input("82.2.9 12:10 남자 이직운")
        self.assertEqual(x["birth_date"], "1982-02-09")
        self.assertEqual(x["gender"], "M")

    @patch("threads_fortune_public._structured_facts")
    def test_public_birth_reply_is_specific_and_never_echoes_birth_date(self, facts):
        facts.return_value = {
            "chart": {
                "year": "임술", "month": "임인", "day": "경진", "hour": "경진",
                "day_master": "경", "day_master_element": "금",
            },
            "advanced": {
                "strength": "신강", "strength_ratio": 63.0,
                "top_ten_gods": [{"name": "편재", "score": 31.0}, {"name": "식신", "score": 25.0}],
            },
            "current_daewoon": {"ko": "계묘", "year_from": 2023, "year_to": 2033},
            "current_year": {
                "ko": "병오", "stem_ten_god": "편관", "branch_ten_god": "정관",
                "interaction_kinds": ["chung"],
            },
            "next_year": {
                "ko": "정미", "stem_ten_god": "정관", "branch_ten_god": "정인",
                "interaction_kinds": [],
            },
            "wealth": {
                "chart_count": 2, "wealth_element": "목",
                "sewoon_years": [{"year": 2028}, {"year": 2029}],
            },
            "love": {"dohwa": "유", "cheonul": ["축", "미"], "hap": "유", "chung": "술"},
        }
        src = "1994.05.24 오전 03:31 남자 재물운"
        out = public_reply(src, "2026-10-04")
        self.assertTrue(out)
        self.assertNotIn("1994.05.24", out)
        self.assertNotIn("03:31", out)
        self.assertNotIn("DM", out)
        self.assertIn("명식", out)
        self.assertIn("현재대운", out)
        self.assertIn("2026 세운", out)
        self.assertIn("재물근거", out)
        self.assertGreaterEqual(len(out.splitlines()), 6)
        self.assertLessEqual(len(out), 470)

    def test_public_zodiac_reply(self):
        out = public_reply("1982년 개띠 재물운 궁금해요", "2026-10-04")
        self.assertTrue(out)
        self.assertIn("개띠", out)
        self.assertIn("재물", out)
        self.assertLessEqual(len(out), 118)


if __name__ == "__main__":
    unittest.main()
