# -*- coding: utf-8 -*-
import datetime as dt
import unittest

from threads_public_saju_event import TEMPLATES, build_text, scheduled_template_id


class PublicSajuEventTest(unittest.TestCase):
    def test_has_ten_templates(self):
        self.assertEqual(len(TEMPLATES), 10)
        self.assertEqual(set(TEMPLATES), set(range(1, 11)))

    def test_all_templates_require_public_birth_input(self):
        for tid in range(1, 11):
            t = build_text(dt.date(2026, 10, 6), tid)
            self.assertIn("생년월일", t)
            self.assertTrue("태어난 시간" in t or "시간" in t)
            self.assertNotIn("인스타 DM", t)
            self.assertNotIn("디엠", t)

    def test_privacy_copy_present(self):
        joined = "\n".join(build_text(dt.date(2026, 10, 6), i) for i in range(1, 11))
        self.assertIn("다시", joined)
        self.assertIn("공개", joined)

    def test_only_template_ten_mentions_optional_sehari(self):
        self.assertNotIn("스하리", build_text(dt.date(2026, 10, 6), 1))
        t = build_text(dt.date(2026, 10, 6), 10)
        self.assertIn("스하리", t)
        self.assertIn("선택", t)

    def test_scheduled_rotation_range(self):
        for offset in range(35):
            d = dt.date(2026, 10, 1) + dt.timedelta(days=offset)
            self.assertIn(scheduled_template_id(d), range(1, 11))


if __name__ == "__main__":
    unittest.main()
