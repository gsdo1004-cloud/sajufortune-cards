# -*- coding: utf-8 -*-
"""Repository policy: Threads automation may publish saju participation prompts only."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
WF = ROOT / ".github" / "workflows"

# These workflows may read Threads data, but must not publish.
READ_ONLY_TOKEN_WORKFLOWS = {
    "ai-news-insights.yml",
    "free-saju-shadow-collect.yml",
    "rce-pilot-insights.yml",
}
PUBLISH_WORKFLOW = "threads-public-saju.yml"
REMOVED_PUBLISHERS = {
    "threads-zodiac-evening.yml",
    "zodiac-ghost.yml",
    "promo-weekly.yml",
    "rce-pilot-publish.yml",
    "ai-news.yml",
}
DENY_PUBLISH_SNIPPETS = (
    "python zodiac_cardnews.py publish",
    "python zodiac_reels.py publish",
    "python promo_publish.py",
    "python rce_pilot_publish.py",
    "publish-threads",
    "ai_news_threads.py --publish",
    "Threads 카드뉴스 발행",
    "스레드 저녁 1편 발행",
    "유령 게시물 발행",
)


class ThreadsPromptOnlyPolicyTest(unittest.TestCase):
    def test_only_prompt_workflow_has_threads_publish_credentials(self):
        allowed = READ_ONLY_TOKEN_WORKFLOWS | {PUBLISH_WORKFLOW}
        offenders = []
        for p in sorted(WF.glob("*.yml")):
            body = p.read_text(encoding="utf-8")
            if "THREADS_ACCESS_TOKEN" in body and p.name not in allowed:
                offenders.append(p.name)
        self.assertEqual(offenders, [], f"unexpected Threads credential workflows: {offenders}")

    def test_known_non_prompt_publishers_are_removed(self):
        present = sorted(name for name in REMOVED_PUBLISHERS if (WF / name).exists())
        self.assertEqual(present, [], f"non-prompt Threads publishers still present: {present}")

    def test_no_non_prompt_workflow_invokes_known_threads_publishers(self):
        offenders = []
        for p in sorted(WF.glob("*.yml")):
            if p.name == PUBLISH_WORKFLOW:
                continue
            body = p.read_text(encoding="utf-8")
            for snippet in DENY_PUBLISH_SNIPPETS:
                if snippet in body:
                    offenders.append(f"{p.name}: {snippet}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_public_saju_is_prompt_only(self):
        body = (WF / PUBLISH_WORKFLOW).read_text(encoding="utf-8")
        self.assertIn("threads_public_saju_event.py", body)
        self.assertNotIn("threads_growth.py", body)
        self.assertNotIn("--send", body)


if __name__ == "__main__":
    unittest.main()
