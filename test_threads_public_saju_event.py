# -*- coding: utf-8 -*-
import datetime as dt
import unittest
from pathlib import Path

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

    def test_templates_warn_against_extra_personal_information(self):
        texts = [build_text(dt.date(2026, 10, 6), i) for i in range(1, 11)]
        for text in texts:
            self.assertIn("전화번호", text)
            self.assertIn("주소", text)
        special = build_text(dt.date(2026, 10, 6), 1, "holiday_mid")
        self.assertIn("전화번호", special)
        self.assertIn("주소", special)

    def test_public_saju_workflow_supports_deduplicated_scheduled_backup(self):
        workflow = (Path(__file__).resolve().parent / ".github" / "workflows" / "threads-public-saju.yml").read_text(encoding="utf-8")
        self.assertIn("scheduled_backup:", workflow)
        self.assertIn("inputs.scheduled_backup", workflow)
        self.assertIn("python threads_public_saju_event.py", workflow)
        self.assertIn("group: threads-growth-main", workflow)

    def test_cloud_reply_scan_is_low_frequency_fallback_after_event_start(self):
        workflow = (Path(__file__).resolve().parent / ".github" / "workflows" / "threads-public-saju-replies.yml").read_text(encoding="utf-8")
        self.assertNotIn("*/5", workflow)
        self.assertIn("30 0-4 * * 2", workflow)
        self.assertIn("30 11-15 * * 0,4", workflow)

    def test_threads_writer_workflows_are_serialized_and_public_scans_scoped(self):
        root = Path(__file__).resolve().parent / ".github" / "workflows"
        growth = (root / "threads-growth.yml").read_text(encoding="utf-8")
        event = (root / "threads-public-saju.yml").read_text(encoding="utf-8")
        replies = (root / "threads-public-saju-replies.yml").read_text(encoding="utf-8")
        for body in (growth, event, replies):
            self.assertIn("group: threads-growth-main", body)
        self.assertIn("--public-saju-only", event)
        self.assertIn("--public-saju-only", replies)

    def test_scheduled_rotation_range(self):
        for offset in range(35):
            d = dt.date(2026, 10, 1) + dt.timedelta(days=offset)
            self.assertIn(scheduled_template_id(d), range(1, 11))


if __name__ == "__main__":
    unittest.main()
