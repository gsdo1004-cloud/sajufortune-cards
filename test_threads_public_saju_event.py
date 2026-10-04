# -*- coding: utf-8 -*-
import datetime as dt
import unittest

from threads_public_saju_event import build_text


class PublicSajuEventTest(unittest.TestCase):
    def test_tuesday_copy(self):
        t = build_text(dt.date(2026, 10, 6))
        self.assertIn("재물·직장", t)
        self.assertIn("생년월일", t)
        self.assertIn("인스타 DM", t)
        self.assertIn("다시 적지 않고", t)

    def test_thursday_copy(self):
        t = build_text(dt.date(2026, 10, 8))
        self.assertIn("사업·변화", t)

    def test_sunday_copy(self):
        t = build_text(dt.date(2026, 10, 11))
        self.assertIn("연애·종합", t)


if __name__ == "__main__":
    unittest.main()
