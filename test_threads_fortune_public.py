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
        self.assertTrue(x["time_known"])

    @patch("threads_fortune_public._preview_sections")
    def test_public_birth_reply_is_detailed_and_never_echoes_birth_date(self, preview):
        preview.return_value = {
            "타고난 성품": "한번 정한 일은 꾸준히 밀고 가지만 판단 전에는 오래 살피는 편입니다.",
            "재물·일": "재물은 서두르기보다 흐름을 살피고 정리하는 편이 좋습니다.",
            "인연·가족": "가까운 사람과의 말 한마디가 관계 흐름을 크게 좌우할 수 있습니다.",
            "2026년 흐름": "움직임과 선택이 중요한 시기라 조건을 비교해 보는 것이 좋습니다.",
            "개운법 한 가지": "큰 결정보다 작은 정리부터 시작하면 흐름을 잡는 데 도움이 됩니다.",
        }
        src = "1994.05.24 오전 03:31 남자 재물운"
        out = public_reply(src, "2026-10-04")
        self.assertTrue(out)
        self.assertNotIn("1994.05.24", out)
        self.assertNotIn("03:31", out)
        self.assertNotIn("DM", out)
        self.assertIn("재물", out)
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
