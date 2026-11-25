# -*- coding: utf-8 -*-
import datetime as dt
import json
import unittest
from pathlib import Path

from unittest.mock import patch, Mock
from threads_public_saju_event import TEMPLATES, HOOK_EXPERIMENT, build_text, scheduled_template_id, experiment_copy, verify_recent_copy


class PublicSajuEventTest(unittest.TestCase):
    def test_has_ten_templates(self):
        self.assertEqual(len(TEMPLATES), 10)
        self.assertEqual(set(TEMPLATES), set(range(1, 11)))

    def test_templates_protect_birth_information(self):
        for tid in range(1, 11):
            t = build_text(dt.date(2026, 10, 6), tid)
            self.assertIn("개인정보 기재 금지", t)
            self.assertNotIn("댓글: 양/음력", t)
            self.assertNotIn("스하리", t)
            self.assertNotIn("디엠", t)

    def test_experiment_is_balanced_and_only_uses_existing_slots(self):
        from collections import Counter
        self.assertEqual(len(HOOK_EXPERIMENT), 14)
        self.assertEqual(Counter(x["arm"] for x in HOOK_EXPERIMENT.values()), {"A": 7, "B": 7})
        self.assertEqual(len({x["text"] for x in HOOK_EXPERIMENT.values()}), 14)
        for day, item in HOOK_EXPERIMENT.items():
            date = dt.date.fromisoformat(day)
            self.assertIn(date.weekday(), (1, 3, 6))
            self.assertEqual(experiment_copy(date, manual=False, template_id=0, occasion=""), item)
            self.assertIsNone(experiment_copy(date, manual=True, template_id=0, occasion=""))
            self.assertIsNone(experiment_copy(date, manual=False, template_id=1, occasion=""))

    def test_recent_post_guard_fails_closed_and_checks_duplicate(self):
        with patch("threads_public_saju_event.requests.get") as get:
            response = Mock()
            get.return_value = response
            response.json.return_value = {"data": [{"id": "1", "text": "같은 문구!"}]}
            with self.assertRaisesRegex(SystemExit, "similar recent"):
                verify_recent_copy("dummy", "같은 문구")
            verify_recent_copy("dummy", "완전히 다른 내용")
            response.json.return_value = {"error": {"code": 1}}
            with self.assertRaisesRegex(SystemExit, "unavailable"):
                verify_recent_copy("dummy", "새 문구")
            get.side_effect = TimeoutError()
            with self.assertRaisesRegex(SystemExit, "verification failed"):
                verify_recent_copy("dummy", "새 문구")

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
