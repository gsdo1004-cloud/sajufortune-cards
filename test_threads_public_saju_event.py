# -*- coding: utf-8 -*-
import datetime as dt
import json
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

    def test_public_saju_workflow_is_post_only(self):
        workflow = (Path(__file__).resolve().parent / ".github" / "workflows" / "threads-public-saju.yml").read_text(encoding="utf-8")
        self.assertIn("scheduled_backup:", workflow)
        self.assertIn("inputs.scheduled_backup", workflow)
        self.assertIn("python threads_public_saju_event.py", workflow)
        self.assertIn("group: threads-growth-main", workflow)
        self.assertNotIn("threads_growth.py", workflow)
        self.assertNotIn("--send", workflow)
        self.assertNotIn("초기 댓글", workflow)

    def test_reply_automation_workflows_are_removed(self):
        root = Path(__file__).resolve().parent / ".github" / "workflows"
        for name in (
            "threads-public-saju-replies.yml",
            "threads-public-saju-tonight.yml",
            "threads-replies.yml",
            "threads-growth.yml",
        ):
            self.assertFalse((root / name).exists(), name)

    def test_growth_config_is_manual_reply_only_defense(self):
        cfg = json.loads((Path(__file__).resolve().parent / "threads_growth_config.json").read_text(encoding="utf-8"))
        self.assertFalse(cfg.get("auto_interactions_enabled", True))
        self.assertEqual(cfg.get("interaction_policy"), "manual_replies_only")
        for key in ("external_daily_cap", "external_per_run", "inbound_daily_cap", "inbound_per_run", "total_daily_cap"):
            self.assertEqual(cfg.get(key), 0, key)
        self.assertFalse(cfg.get("keyword_discovery_enabled", True))

    def test_scheduled_rotation_range(self):
        for offset in range(35):
            d = dt.date(2026, 10, 1) + dt.timedelta(days=offset)
            self.assertIn(scheduled_template_id(d), range(1, 11))


if __name__ == "__main__":
    unittest.main()
