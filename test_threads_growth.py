# -*- coding: utf-8 -*-
import datetime as dt
import unittest
import tempfile
from unittest import mock
from pathlib import Path

import threads_growth as g


_TEST_TMP = None
_ORIGINAL_PATHS = {}


def setUpModule():
    global _TEST_TMP
    _TEST_TMP = tempfile.TemporaryDirectory(prefix="threads_growth_tests_")
    root = Path(_TEST_TMP.name)
    for name in ("STATE_PATH", "PAUSE_PATH", "REPORT_PATH", "CAP_PATH"):
        _ORIGINAL_PATHS[name] = getattr(g, name)
    g.STATE_PATH = root / "threads_growth_state.json"
    g.PAUSE_PATH = root / "threads_growth_PAUSED.json"
    g.REPORT_PATH = root / "threads_growth_report.md"
    g.CAP_PATH = root / "threads_growth_capabilities.json"


def tearDownModule():
    for name, value in _ORIGINAL_PATHS.items():
        setattr(g, name, value)
    if _TEST_TMP is not None:
        _TEST_TMP.cleanup()


def _test_path(name: str) -> Path:
    if _TEST_TMP is None:
        raise RuntimeError("test tempdir is not initialized")
    return Path(_TEST_TMP.name) / name


class GrowthSafetyTests(unittest.TestCase):
    def setUp(self):
        self.cfg = g.load_config()
        self.state = g.default_state()

    def test_quality_rejects_promo_and_urls(self):
        for text in [
            "자세한 내용은 https://example.com 에서 보세요",
            "제 프로필 링크에서 무료운세 보세요",
            "@someone 정말 좋은 해석이네요",
            "#사주 좋은 글 감사합니다",
        ]:
            ok, _ = g.quality_gate(text, self.cfg, self.state, external=True)
            self.assertFalse(ok, text)

    def test_quality_accepts_specific_nonpromo_reply(self):
        text = "같은 재성이라도 월령과 강약을 같이 보면 해석이 조금 달라질 수 있겠네요."
        ok, reason = g.quality_gate(text, self.cfg, self.state, external=True)
        self.assertTrue(ok, reason)

    def test_duplicate_rejected(self):
        text = "대운만 보기보다 세운의 충합까지 같이 보면 시점이 더 선명해지더군요."
        self.state["sent"].append({"text_hash": g.text_hash(text)})
        ok, reason = g.quality_gate(text, self.cfg, self.state, external=True)
        self.assertFalse(ok)
        self.assertEqual(reason, "duplicate")

    def test_daily_external_cap(self):
        b = g.today_bucket(self.state, dt.datetime.now(dt.timezone.utc))
        b["external"] = self.cfg["external_daily_cap"]
        self.assertFalse(g.can_send_external(self.cfg, self.state, "saju.pharmacy"))

    def test_per_target_cap(self):
        b = g.today_bucket(self.state)
        b["per_target"]["saju.pharmacy"] = 1
        self.assertFalse(g.can_send_external(self.cfg, self.state, "saju.pharmacy"))


    def test_near_duplicate_rejected(self):
        old = "대운만 보기보다 세운의 충합까지 함께 보면 시점이 더 선명해집니다."
        self.state["sent"].append({"text_hash": g.text_hash(old), "text": old})
        new = "대운만 보기보다 세운의 충합까지 같이 보면 시점이 더 선명해집니다."
        ok, reason = g.quality_gate(new, self.cfg, self.state, external=True)
        self.assertFalse(ok)
        self.assertEqual(reason, "near_duplicate")

    def test_relevance(self):
        self.assertGreater(g.relevant_score("오늘은 정재와 재물운을 같이 봅니다", self.cfg), 0)
        self.assertEqual(g.relevant_score("야구 경기 결과", self.cfg), 0)


    def test_public_saju_reply_waits_for_human_paced_delay(self):
        cfg = dict(self.cfg)
        cfg["public_saju_reply_min_delay_minutes"] = 60
        cfg["public_saju_reply_max_delay_minutes"] = 60
        ts = (g.utcnow() - dt.timedelta(minutes=30)).isoformat()
        cand = g.Candidate(
            id="birth-delay-1",
            username="visitor",
            text="양력 1982.02.09 12:10 남자 이직운",
            timestamp=ts,
            kind="inbound",
        )
        ready, required, age_min = g.public_saju_ready(cand, cfg)
        self.assertFalse(ready)
        self.assertEqual(required, 60)
        self.assertLess(age_min, 60)

    def test_public_saju_reply_becomes_ready_after_delay(self):
        cfg = dict(self.cfg)
        cfg["public_saju_reply_min_delay_minutes"] = 35
        cfg["public_saju_reply_max_delay_minutes"] = 35
        ts = (g.utcnow() - dt.timedelta(minutes=80)).isoformat()
        cand = g.Candidate(
            id="birth-delay-2",
            username="visitor",
            text="음력 1994-05-24 오전 03:31 여자 재물운",
            timestamp=ts,
            kind="inbound",
        )
        ready, required, age_min = g.public_saju_ready(cand, cfg)
        self.assertTrue(ready)
        self.assertEqual(required, 35)
        self.assertGreaterEqual(age_min, 35)

    def test_general_comment_is_not_forced_to_wait(self):
        cand = g.Candidate(
            id="normal-1",
            username="visitor",
            text="글 잘 봤어요. 개띠 흐름도 궁금해요",
            timestamp=g.utcnow().isoformat(),
            kind="inbound",
        )
        ready, required, _ = g.public_saju_ready(cand, self.cfg)
        self.assertTrue(ready)
        self.assertEqual(required, 0)


class RevenueGateTests(unittest.TestCase):
    def test_external_never_gets_revenue_cta(self):
        c = g.Candidate(id="external-1", username="other", text="무료 사주 궁금", timestamp="2026-09-17T00:00:00Z", kind="external")
        cfg = {"revenue_intent_keywords": ["무료"], "revenue_share_target": 1.0, "revenue_link_daily_cap": 1}
        text, used = g.maybe_add_revenue_cta("대화 답글", c, cfg, {"sent": []})
        self.assertFalse(used)
        self.assertEqual(text, "대화 답글")

    def test_high_intent_inbound_can_get_tracked_cta_when_gate_selected(self):
        c = g.Candidate(id="inbound-fixed", username="visitor", text="제 사주 무료로 어디서 확인해요?", timestamp="2026-09-17T00:00:00Z", kind="inbound")
        cfg = {"revenue_intent_keywords": ["무료", "확인"], "revenue_share_target": 1.0, "revenue_link_daily_cap": 1}
        text, used = g.maybe_add_revenue_cta("확인해보실 수 있어요.", c, cfg, {"sent": []})
        self.assertTrue(used)
        self.assertIn("utm_source=threads", text)
        self.assertIn("sajufortune.kr", text)

    def test_daily_revenue_link_cap_blocks_second_cta(self):
        c = g.Candidate(id="inbound-2", username="visitor", text="재물운 확인하고 싶어요", timestamp="2026-09-17T00:00:00Z", kind="inbound")
        cfg = {"revenue_intent_keywords": ["재물운"], "revenue_share_target": 1.0, "revenue_link_daily_cap": 1}
        state = {"sent": [{"date_kst": g.date_key(), "revenue_cta": True}]}
        text, used = g.maybe_add_revenue_cta("답글", c, cfg, state)
        self.assertFalse(used)
        self.assertEqual(text, "답글")

    def test_general_inbound_can_get_soft_profile_cta_after_warmup(self):
        c = g.Candidate(id="inbound-soft", username="visitor", text="설명이 이해가 잘 되네요", timestamp="2026-09-20T00:00:00Z", kind="inbound")
        cfg = {
            "revenue_intent_keywords": ["무료"],
            "revenue_share_target": 0.0,
            "revenue_link_daily_cap": 2,
            "revenue_daily_cap": 3,
            "revenue_profile_share_target": 1.0,
            "revenue_profile_daily_cap": 2,
        }
        text, used = g.maybe_add_revenue_cta("답글입니다.", c, cfg, {"sent": []})
        self.assertTrue(used)
        self.assertIn("프로필 첫 버튼", text)
        self.assertNotIn("https://", text)

    def test_total_promo_daily_cap_blocks_more_ctas(self):
        c = g.Candidate(id="inbound-cap", username="visitor", text="제 사주가 궁금해요", timestamp="2026-09-20T00:00:00Z", kind="inbound")
        cfg = {
            "revenue_intent_keywords": ["궁금"],
            "revenue_share_target": 1.0,
            "revenue_link_daily_cap": 3,
            "revenue_daily_cap": 3,
            "revenue_profile_share_target": 1.0,
            "revenue_profile_daily_cap": 3,
        }
        state = {"sent": [
            {"date_kst": g.date_key(), "revenue_cta": True, "text": "https://sajufortune.kr/a"},
            {"date_kst": g.date_key(), "revenue_cta": True, "text": "프로필 첫 버튼에서 확인"},
            {"date_kst": g.date_key(), "revenue_cta": True, "text": "https://sajufortune.kr/b"},
        ]}
        text, used = g.maybe_add_revenue_cta("답글", c, cfg, state)
        self.assertFalse(used)
        self.assertEqual(text, "답글")


class ExternalGrowthScalingTests(unittest.TestCase):
    def setUp(self):
        self.cfg = g.load_config()
        self.state = g.default_state()
        self.now = dt.datetime(2026, 10, 10, 3, 0, tzinfo=dt.timezone.utc)

    def test_config_starts_at_eight_and_caps_at_twenty(self):
        self.assertEqual(self.cfg["external_growth_stages"], [8, 12, 20])
        self.assertEqual(self.cfg["external_per_run"], 2)
        self.assertEqual(g.effective_external_daily_cap(self.cfg, self.state, self.now), 8)

    def test_stable_seven_day_window_promotes_to_twelve(self):
        cfg = dict(self.cfg)
        cfg.update({
            "external_growth_stage_days": 7,
            "external_growth_min_stage_sends": 14,
            "external_growth_min_measured": 8,
            "external_growth_min_engagement_rate": 0.02,
            "external_growth_max_error_rate": 0.05,
        })
        self.state["external_growth"] = {
            "stage_index": 0,
            "stage_started_kst": "2026-10-03",
            "history": [],
        }
        for d in range(3, 10):
            self.state["days"][f"2026-10-{d:02d}"] = {
                "external": 2,
                "inbound": 0,
                "nested": 0,
                "total": 2,
                "per_target": {},
                "external_measured": 2,
                "external_engaged": 1 if d == 9 else 0,
                "external_errors": 0,
                "external_safety_stops": 0,
            }
        summary = g.maybe_advance_external_stage(cfg, self.state, self.now)
        self.assertTrue(summary["promoted"])
        self.assertEqual(summary["stage_index"], 1)
        self.assertEqual(summary["daily_cap"], 12)

    def test_safety_stop_blocks_stage_promotion(self):
        cfg = dict(self.cfg)
        cfg.update({
            "external_growth_stage_days": 7,
            "external_growth_min_stage_sends": 7,
            "external_growth_min_measured": 7,
            "external_growth_min_engagement_rate": 0.0,
            "external_growth_max_error_rate": 1.0,
        })
        self.state["external_growth"] = {
            "stage_index": 0,
            "stage_started_kst": "2026-10-03",
            "history": [],
        }
        for d in range(3, 10):
            self.state["days"][f"2026-10-{d:02d}"] = {
                "external": 1,
                "inbound": 0,
                "nested": 0,
                "total": 1,
                "per_target": {},
                "external_measured": 1,
                "external_engaged": 0,
                "external_errors": 0,
                "external_safety_stops": 1 if d == 8 else 0,
            }
        summary = g.maybe_advance_external_stage(cfg, self.state, self.now)
        self.assertFalse(summary["promoted"])
        self.assertEqual(summary["stage_index"], 0)
        self.assertEqual(summary["daily_cap"], 8)

    def test_can_send_external_uses_current_stage_cap(self):
        self.state["external_growth"] = {
            "stage_index": 1,
            "stage_started_kst": g.date_key(self.now),
            "history": [],
        }
        bucket = g.today_bucket(self.state, self.now)
        bucket["external"] = 11
        bucket["total"] = 11
        self.assertTrue(g.can_send_external(self.cfg, self.state, "new.author", self.now))
        bucket["external"] = 12
        bucket["total"] = 12
        self.assertFalse(g.can_send_external(self.cfg, self.state, "another.author", self.now))

    def test_conversation_signal_prefers_real_question_over_bait(self):
        question = "재물운을 볼 때 대운과 세운 중 어느 쪽을 먼저 보시나요? 요즘 이 부분이 궁금합니다."
        bait = "사주 이벤트 할인 중입니다. 댓글 달면 DM 드려요. 지금 구매하세요."
        self.assertGreater(
            g.conversation_signal_score(question, self.cfg),
            g.conversation_signal_score(bait, self.cfg),
        )

    def test_rank_external_candidates_keeps_best_post_per_author(self):
        rows = [
            g.Candidate(id="a-low", username="same", text="사주 글", timestamp="", kind="external", score=80),
            g.Candidate(id="a-high", username="same", text="재물운이 왜 다를까요?", timestamp="", kind="external", score=120),
            g.Candidate(id="b", username="other", text="대운과 세운 질문", timestamp="", kind="external", score=100),
        ]
        ranked = g.rank_external_candidates(rows)
        self.assertEqual([x.id for x in ranked], ["a-high", "b"])

    def test_record_send_keeps_discovery_metadata(self):
        c = g.Candidate(
            id="post-1", username="writer", text="재물운이 궁금합니다", timestamp=self.now.isoformat(),
            kind="external", score=123.0, source_query="재물운", search_type="TOP",
            relevance=2, conversation_signal=5.0,
        )
        g.record_send(
            self.state,
            c,
            "재물운은 세운과 대운을 같이 보면 시점이 더 또렷해질 수 있습니다.",
            {"id": "reply-1", "replied_to": {"id": "post-1"}},
            dry_run=False,
            now=self.now,
        )
        row = self.state["sent"][-1]
        self.assertEqual(row["source_query"], "재물운")
        self.assertEqual(row["search_type"], "TOP")
        self.assertEqual(row["date_kst"], g.date_key(self.now))

    def test_external_insights_are_counted_once_and_learnable(self):
        c = g.Candidate(
            id="post-2", username="writer2", text="대운 질문", timestamp=self.now.isoformat(),
            kind="external", score=110.0, source_query="대운", search_type="RECENT",
            relevance=2, conversation_signal=4.0,
        )
        g.record_send(
            self.state, c, "대운과 세운을 함께 보면 변곡점이 더 잘 보일 수 있어요.",
            {"id": "reply-2", "replied_to": {"id": "post-2"}}, dry_run=False, now=self.now,
        )
        row = self.state["sent"][-1]
        metrics = {"views": 30, "likes": 2, "replies": 1, "reposts": 0, "quotes": 0, "shares": 0}
        g.record_external_insights(self.state, row, metrics, now=self.now + dt.timedelta(hours=3))
        g.record_external_insights(self.state, row, metrics, now=self.now + dt.timedelta(hours=4))
        bucket = self.state["days"][g.date_key(self.now)]
        self.assertEqual(bucket["external_measured"], 1)
        self.assertEqual(bucket["external_engaged"], 1)
        self.assertEqual(bucket["external_replies"], 1)
        self.assertGreater(g.source_performance_bonus(self.state, "대운", "RECENT"), 0)


class ExternalDiscoveryIntegrationTests(unittest.TestCase):
    def test_keyword_discovery_ranks_conversation_and_keeps_metadata(self):
        class FakeAPI:
            def get(self, path, params=None):
                if path != "keyword_search":
                    raise AssertionError(path)
                ts = g.utcnow().isoformat()
                return {"data": [
                    {"id": "q1", "username": "same", "text": "사주 재물운을 볼 때 대운과 세운 중 무엇을 먼저 봐야 하나요? 요즘 정말 궁금합니다.", "timestamp": ts, "permalink": "https://threads.net/q1", "is_reply": False, "has_replies": True},
                    {"id": "q2", "username": "same", "text": "사주 재물운 해석에 관한 일반적인 정리 글을 오늘 공유합니다. 참고하시면 됩니다.", "timestamp": ts, "permalink": "https://threads.net/q2", "is_reply": False, "has_replies": False},
                    {"id": "bait", "username": "promo", "text": "사주 재물운 이벤트 할인 중입니다. 댓글 달면 DM 드리고 지금 구매하면 혜택이 있습니다.", "timestamp": ts, "permalink": "https://threads.net/bait", "is_reply": False, "has_replies": True},
                ]}

        cfg = dict(g.load_config())
        cfg.update({
            "topic_keywords": ["사주", "재물운"],
            "keyword_search_types": ["TOP"],
            "keyword_discovery_min_relevance": 1,
        })
        rows = g.external_candidates(FakeAPI(), cfg, g.default_state(), {"keyword_search": True, "profile_posts": False})
        same = [x for x in rows if x.username == "same"]
        self.assertEqual(len(same), 1)
        self.assertEqual(same[0].id, "q1")
        self.assertEqual(same[0].search_type, "TOP")
        self.assertTrue(same[0].source_query)
        self.assertGreaterEqual(same[0].relevance, 2)
        self.assertGreater(same[0].conversation_signal, 0)
        self.assertGreater(rows[0].score, next(x.score for x in rows if x.id == "bait"))

    def test_collect_external_insights_updates_learning_state(self):
        class FakeAPI:
            def __init__(self):
                self.calls = []
            def get(self, path, params=None):
                self.calls.append((path, params))
                return {"data": [
                    {"name": "views", "values": [{"value": 45}]},
                    {"name": "likes", "values": [{"value": 3}]},
                    {"name": "replies", "values": [{"value": 1}]},
                    {"name": "reposts", "values": [{"value": 0}]},
                    {"name": "quotes", "values": [{"value": 0}]},
                    {"name": "shares", "values": [{"value": 0}]},
                ]}

        cfg = dict(g.load_config())
        cfg["external_insights_min_age_hours"] = 2
        cfg["external_insights_refresh_hours"] = 12
        state = g.default_state()
        sent_at = g.utcnow() - dt.timedelta(hours=3)
        c = g.Candidate(
            id="target-i", username="author-i", text="사주 재물운 질문입니다", timestamp=sent_at.isoformat(),
            kind="external", score=120, source_query="재물운", search_type="TOP", relevance=2,
            conversation_signal=5,
        )
        g.record_send(state, c, "대운과 세운을 같이 보면 시점이 더 선명할 수 있습니다.",
                      {"id": "reply-i", "replied_to": {"id": "target-i"}}, dry_run=False, now=sent_at)
        api = FakeAPI()
        result = g.collect_external_insights(api, cfg, state, now=g.utcnow())
        self.assertEqual(result["measured"], 1)
        self.assertEqual(len(api.calls), 1)
        self.assertEqual(state["sent"][-1]["external_metrics"]["replies"], 1)
        bucket = state["days"][g.date_key(sent_at)]
        self.assertEqual(bucket["external_engaged"], 1)


    def test_collect_external_insights_network_failure_is_nonfatal(self):
        class TimeoutAPI:
            def get(self, path, params=None):
                import requests
                raise requests.Timeout("transient")

        cfg = dict(g.load_config())
        cfg["external_insights_min_age_hours"] = 0
        state = g.default_state()
        sent_at = g.utcnow() - dt.timedelta(hours=3)
        c = g.Candidate(
            id="target-timeout", username="author-timeout", text="재물운 질문", timestamp=sent_at.isoformat(),
            kind="external", source_query="재물운", search_type="RECENT", relevance=1,
        )
        g.record_send(
            state, c, "재물운은 시기를 같이 보면 좋습니다.",
            {"id": "reply-timeout", "replied_to": {"id": "target-timeout"}}, dry_run=False, now=sent_at,
        )
        result = g.collect_external_insights(TimeoutAPI(), cfg, state, now=g.utcnow())
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["measured"], 0)



class ExternalRuntimeSafetyTests(unittest.TestCase):
    def test_pause_file_disables_actual_api_publish(self):
        cfg = dict(g.load_config())
        state = g.default_state()
        candidate = g.Candidate(
            id="in-1", username="visitor", text="개띠도 궁금해요", timestamp=g.utcnow().isoformat(), kind="inbound"
        )
        marker = _test_path("_test_threads_pause.json")
        marker.write_text('{"reason":"test"}', encoding="utf-8")
        try:
            with mock.patch.object(g, "PAUSE_PATH", marker), \
                 mock.patch.object(g, "inbound_candidates", return_value=[candidate]), \
                 mock.patch.object(g, "generate_reply", return_value="개띠 흐름도 함께 살펴볼 수 있습니다."), \
                 mock.patch.object(g, "publish_reply", return_value={"id":"should-not-send", "replied_to":{"id":"in-1"}}) as publish:
                result = g.run_growth(
                    object(), cfg, state, {"read_replies": True, "profile_posts": False, "keyword_search": False},
                    send=True, do_external=False, do_inbound=True,
                )
            publish.assert_not_called()
            self.assertFalse(result["send"])
        finally:
            marker.unlink(missing_ok=True)

    def test_external_publish_error_is_recorded_for_stage_gate(self):
        cfg = dict(g.load_config())
        state = g.default_state()
        candidate = g.Candidate(
            id="ex-err", username="writer", text="사주 재물운이 궁금합니다. 어떻게 보시나요?",
            timestamp=g.utcnow().isoformat(), kind="external", score=100,
            source_query="재물운", search_type="RECENT", relevance=2, conversation_signal=4,
        )
        with mock.patch.object(g, "external_candidates", return_value=[candidate]), \
             mock.patch.object(g, "generate_reply", return_value="대운과 세운을 같이 보면 시점이 조금 더 선명해질 수 있어요."), \
             mock.patch.object(g, "publish_reply", side_effect=g.APIError("temporary")):
            result = g.run_growth(
                object(), cfg, state,
                {"read_replies": False, "profile_posts": False, "keyword_search": True, "token_scopes": []},
                send=True, do_external=True, do_inbound=False,
            )
        self.assertEqual(result["day"]["external_errors"], 1)
        self.assertIn("external_growth", result)
        self.assertEqual(result["external_growth"]["daily_cap"], 8)


class ExternalReviewFixTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(g.load_config())
        self.state = g.default_state()

    def test_inbound_location_mismatch_pause_stops_external_publish(self):
        inbound = g.Candidate(id="in-mismatch", username="visitor", text="개띠 궁금", timestamp=g.utcnow().isoformat(), kind="inbound")
        external = g.Candidate(id="ex-after", username="writer", text="사주 재물운이 궁금합니다. 어떻게 보나요?", timestamp=g.utcnow().isoformat(), kind="external", score=100)
        marker = _test_path("_test_pause_midrun.json")
        try:
            def fake_publish(api, candidate, text):
                if candidate.id == "in-mismatch":
                    marker.write_text('{"reason":"reply_location_mismatch"}', encoding="utf-8")
                    raise g.LocationMismatch("wrong target")
                raise AssertionError("external publish must not run after PAUSE")

            with mock.patch.object(g, "PAUSE_PATH", marker), \
                 mock.patch.object(g, "inbound_candidates", return_value=[inbound]), \
                 mock.patch.object(g, "external_candidates", return_value=[external]), \
                 mock.patch.object(g, "generate_reply", return_value="맥락 있는 답변입니다."), \
                 mock.patch.object(g, "publish_reply", side_effect=fake_publish) as publish:
                result = g.run_growth(
                    object(), self.cfg, self.state,
                    {"read_replies": True, "keyword_search": True, "profile_posts": False, "token_scopes": []},
                    send=True, do_external=True, do_inbound=True,
                )
            self.assertEqual(publish.call_count, 1)
            self.assertTrue(result["paused"])
            self.assertEqual(result["day"]["external"], 0)
        finally:
            marker.unlink(missing_ok=True)

    def test_uncertain_publish_is_counted_and_pauses_future_writes(self):
        c = g.Candidate(
            id="ex-uncertain", username="writer-u", text="재물운이 궁금합니다", timestamp=g.utcnow().isoformat(),
            kind="external", score=100, source_query="재물운", search_type="RECENT", relevance=1,
        )
        marker = _test_path("_test_pause_uncertain.json")
        try:
            with mock.patch.object(g, "PAUSE_PATH", marker), \
                 mock.patch.object(g, "external_candidates", return_value=[c]), \
                 mock.patch.object(g, "generate_reply", return_value="재물운은 흐름과 시기를 같이 보는 편이 좋습니다."), \
                 mock.patch.object(g, "publish_reply", side_effect=g.UncertainPublish("reply-u", "verification unavailable")):
                result = g.run_growth(
                    object(), self.cfg, self.state,
                    {"read_replies": False, "keyword_search": True, "profile_posts": False, "token_scopes": []},
                    send=True, do_external=True, do_inbound=False,
                )
            self.assertTrue(marker.exists())
            self.assertEqual(result["day"]["external"], 1)
            row = self.state["sent"][-1]
            self.assertEqual(row["effect"], "UNKNOWN")
            self.assertEqual(row["reply_id"], "reply-u")
            self.assertFalse(g.can_send_external(self.cfg, self.state, "writer-u"))
        finally:
            marker.unlink(missing_ok=True)

    def test_insights_limit_counts_failed_attempts(self):
        class AlwaysFailAPI:
            def __init__(self): self.calls = 0
            def get(self, path, params=None):
                self.calls += 1
                raise g.APIError("no insight")

        self.cfg["external_insights_min_age_hours"] = 0
        self.cfg["external_insights_refresh_hours"] = 0
        self.cfg["external_insights_per_run"] = 3
        now = g.utcnow()
        for i in range(8):
            c = g.Candidate(id=f"t-{i}", username=f"u-{i}", text="재물운 질문", timestamp=(now-dt.timedelta(hours=3)).isoformat(), kind="external")
            g.record_send(self.state, c, "맥락 있는 답변입니다.", {"id": f"r-{i}", "replied_to": {"id": f"t-{i}"}}, dry_run=False, now=now-dt.timedelta(hours=3))
        api = AlwaysFailAPI()
        result = g.collect_external_insights(api, self.cfg, self.state, now=now)
        self.assertEqual(api.calls, 3)
        self.assertEqual(result["attempted"], 3)
        self.assertEqual(result["failed"], 3)

    def test_insight_metrics_are_monotonic_across_decrease_and_recovery(self):
        now = g.utcnow()
        c = g.Candidate(id="t-m", username="u-m", text="대운 질문", timestamp=now.isoformat(), kind="external")
        g.record_send(self.state, c, "맥락 있는 답변입니다.", {"id": "r-m", "replied_to": {"id": "t-m"}}, dry_run=False, now=now)
        row = self.state["sent"][-1]
        g.record_external_insights(self.state, row, {"likes": 3, "replies": 1}, now=now+dt.timedelta(hours=2))
        g.record_external_insights(self.state, row, {"likes": 0, "replies": 0}, now=now+dt.timedelta(hours=3))
        g.record_external_insights(self.state, row, {"likes": 3, "replies": 1}, now=now+dt.timedelta(hours=4))
        b = self.state["days"][g.date_key(now)]
        self.assertEqual(b["external_measured"], 1)
        self.assertEqual(b["external_engaged"], 1)
        self.assertEqual(b["external_likes"], 3)
        self.assertEqual(b["external_replies"], 1)
        self.assertEqual(row["external_metrics"]["likes"], 3)

    def test_keyword_discovery_api_error_counts_for_growth_gate(self):
        class FailSearchAPI:
            def get(self, path, params=None):
                raise g.APIError("search down")
        cfg = dict(self.cfg)
        cfg["topic_keywords"] = ["사주"]
        cfg["keyword_search_types"] = ["RECENT"]
        with self.assertRaises(g.CandidateScanError):
            g.external_candidates(FailSearchAPI(), cfg, self.state, {"profile_posts": False, "keyword_search": True})
        self.assertEqual(g.today_bucket(self.state)["external_errors"], 1)

    def test_non_api_backend_cannot_queue_or_publish(self):
        cfg = dict(self.cfg)
        cfg["publisher_backend"] = "android_ui"
        external = g.Candidate(id="ex-ui", username="writer-ui", text="사주 질문입니다", timestamp=g.utcnow().isoformat(), kind="external", score=100)
        with mock.patch.object(g, "external_candidates", return_value=[external]), \
             mock.patch.object(g, "generate_reply", return_value="맥락 있는 답변입니다."), \
             mock.patch.object(g, "publish_reply") as publish:
            result = g.run_growth(
                object(), cfg, self.state,
                {"read_replies": False, "keyword_search": True, "profile_posts": False, "token_scopes": []},
                send=True, do_external=True, do_inbound=False,
            )
        publish.assert_not_called()
        self.assertFalse(result["send"])
        self.assertEqual(result.get("hold_reason"), "publisher_backend_not_api")


class ExternalSafetyHardeningTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(g.load_config())
        self.state = g.default_state()

    def test_external_gate_blocks_bare_domain_and_promotional_install_text(self):
        samples = [
            "자세한 내용은 example.com 에서 확인해 보세요",
            "추가 설명은 fortune.xyz 에 정리했습니다",
            "현담 앱을 설치해 보세요. 할인 이벤트 진행 중입니다.",
        ]
        for text in samples:
            ok, _ = g.quality_gate(text, self.cfg, self.state, external=True)
            self.assertFalse(ok, text)

    def test_corrupt_state_file_fails_closed(self):
        tmp = _test_path("_test_corrupt_growth_state.json")
        tmp.write_text('{"schema":1,"days":', encoding="utf-8")
        try:
            with mock.patch.object(g, "STATE_PATH", tmp):
                with self.assertRaises(g.StateCorruption):
                    g.load_state()
        finally:
            tmp.unlink(missing_ok=True)

    def test_missing_growth_fields_migrate_without_resetting_existing_counts(self):
        tmp = _test_path("_test_legacy_growth_state.json")
        legacy = {
            "schema": 1,
            "handled_inbound_ids": ["i1"],
            "external_target_ids": ["e1"],
            "sent": [{"target_id": "e1", "kind": "external"}],
            "days": {g.date_key(): {"external": 3, "inbound": 1, "nested": 0, "total": 4, "per_target": {"author": 1}}},
            "last_run_at": None,
        }
        tmp.write_text(__import__('json').dumps(legacy), encoding="utf-8")
        try:
            with mock.patch.object(g, "STATE_PATH", tmp):
                state = g.load_state()
            self.assertEqual(state["days"][g.date_key()]["external"], 3)
            self.assertEqual(state["external_target_ids"], ["e1"])
            self.assertIn("external_growth", state)
        finally:
            tmp.unlink(missing_ok=True)

    def test_second_stable_window_promotes_twelve_to_twenty(self):
        cfg = dict(self.cfg)
        cfg.update({
            "external_growth_stage_days": 7,
            "external_growth_min_stage_sends": 14,
            "external_growth_min_measured": 8,
            "external_growth_min_engagement_rate": 0.02,
            "external_growth_max_error_rate": 0.05,
            "external_growth_max_insight_failure_rate": 0.20,
        })
        now = dt.datetime(2026, 10, 24, 3, 0, tzinfo=dt.timezone.utc)
        self.state["external_growth"] = {"stage_index": 1, "stage_started_kst": "2026-10-17", "history": []}
        for day in range(17, 24):
            self.state["days"][f"2026-10-{day:02d}"] = {
                "external": 2, "inbound": 0, "nested": 0, "total": 2, "per_target": {},
                "external_measured": 2, "external_engaged": 1, "external_errors": 0,
                "external_safety_stops": 0, "external_insight_failures": 0,
            }
        result = g.maybe_advance_external_stage(cfg, self.state, now)
        self.assertTrue(result["promoted"])
        self.assertEqual(result["daily_cap"], 20)
        self.assertEqual(result["stage_index"], 2)

    def test_invalid_insights_payload_is_failure_not_measurement(self):
        class EmptyAPI:
            def get(self, path, params=None): return {"data": []}
        cfg = dict(self.cfg)
        cfg["external_insights_min_age_hours"] = 0
        cfg["external_insights_refresh_hours"] = 0
        now = g.utcnow()
        c = g.Candidate(id="t-empty", username="u-empty", text="재물운 질문", timestamp=now.isoformat(), kind="external")
        g.record_send(self.state, c, "맥락 있는 답변입니다.", {"id":"r-empty","replied_to":{"id":"t-empty"}}, dry_run=False, now=now-dt.timedelta(hours=3))
        result = g.collect_external_insights(EmptyAPI(), cfg, self.state, now=now)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["measured"], 0)
        self.assertEqual(self.state["days"][g.date_key(now-dt.timedelta(hours=3))]["external_insight_failures"], 1)

    def test_reservation_counts_before_publish_and_finalize_does_not_double_count(self):
        now = g.utcnow()
        c = g.Candidate(id="t-res", username="u-res", text="재물운 질문", timestamp=now.isoformat(), kind="external")
        row = g.reserve_send(self.state, c, "맥락 있는 답변입니다.", now=now, persist=False)
        self.assertEqual(g.today_bucket(self.state, now)["external"], 1)
        self.assertEqual(row["effect"], "PENDING")
        self.assertFalse(g.can_send_external(self.cfg, self.state, "u-res", now))
        g.finalize_reserved_send(self.state, row, {"id":"r-res","replied_to":{"id":"t-res"}}, effect="CONFIRMED", persist=False)
        self.assertEqual(g.today_bucket(self.state, now)["external"], 1)
        self.assertEqual(row["effect"], "CONFIRMED")
        self.assertEqual(row["reply_id"], "r-res")

    def test_release_reservation_restores_cap_after_definite_failure(self):
        now = g.utcnow()
        c = g.Candidate(id="t-release", username="u-release", text="재물운 질문", timestamp=now.isoformat(), kind="external")
        row = g.reserve_send(self.state, c, "맥락 있는 답변입니다.", now=now, persist=False)
        g.release_reserved_send(self.state, row, persist=False)
        self.assertEqual(g.today_bucket(self.state, now)["external"], 0)
        self.assertTrue(g.can_send_external(self.cfg, self.state, "u-release", now))
        self.assertNotIn("t-release", self.state["external_target_ids"])

    def test_post_timeout_becomes_uncertain_and_creates_pause(self):
        class TimeoutPostAPI:
            def get(self, path, params=None):
                if path == "target-timeout": return {"id":"target-timeout"}
                return {"data": []}
            def post(self, path, data=None):
                import requests
                raise requests.Timeout("post timeout")
        marker = _test_path("_test_post_timeout_pause.json")
        c = g.Candidate(id="target-timeout", username="u", text="재물운 질문", timestamp=g.utcnow().isoformat(), kind="external")
        try:
            with mock.patch.object(g, "PAUSE_PATH", marker):
                with self.assertRaises(g.UncertainPublish):
                    g.publish_reply(TimeoutPostAPI(), c, "맥락 있는 답변입니다.")
            self.assertTrue(marker.exists())
        finally:
            marker.unlink(missing_ok=True)


class ExternalReservationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(g.load_config())
        self.state = g.default_state()

    def test_run_growth_success_uses_one_reservation_and_one_count(self):
        candidate = g.Candidate(
            id="ex-success", username="writer-success", text="사주 재물운이 궁금합니다. 어떻게 보나요?",
            timestamp=g.utcnow().isoformat(), kind="external", score=100,
            source_query="재물운", search_type="RECENT", relevance=2, conversation_signal=4,
        )
        marker = _test_path("_test_no_pause_success.json")
        marker.unlink(missing_ok=True)
        try:
            with mock.patch.object(g, "PAUSE_PATH", marker), \
                 mock.patch.object(g, "external_candidates", return_value=[candidate]), \
                 mock.patch.object(g, "generate_reply", return_value="대운과 세운을 같이 보면 시점이 조금 더 선명할 수 있습니다."), \
                 mock.patch.object(g, "publish_reply", return_value={"id":"reply-success","replied_to":{"id":"ex-success"}}):
                result = g.run_growth(
                    object(), self.cfg, self.state,
                    {"read_replies": False, "keyword_search": True, "profile_posts": False, "token_scopes": []},
                    send=True, do_external=True, do_inbound=False,
                )
            self.assertEqual(result["day"]["external"], 1)
            self.assertEqual(result["day"]["total"], 1)
            self.assertEqual(len(self.state["sent"]), 1)
            self.assertEqual(self.state["sent"][0]["effect"], "CONFIRMED")
            self.assertEqual(self.state["sent"][0]["reply_id"], "reply-success")
        finally:
            marker.unlink(missing_ok=True)

    def test_run_growth_definite_external_failure_releases_reservation(self):
        candidate = g.Candidate(
            id="ex-fail-release", username="writer-fail", text="사주 재물운이 궁금합니다. 어떻게 보나요?",
            timestamp=g.utcnow().isoformat(), kind="external", score=100,
            source_query="재물운", search_type="RECENT", relevance=2, conversation_signal=4,
        )
        marker = _test_path("_test_no_pause_fail.json")
        marker.unlink(missing_ok=True)
        try:
            with mock.patch.object(g, "PAUSE_PATH", marker), \
                 mock.patch.object(g, "external_candidates", return_value=[candidate]), \
                 mock.patch.object(g, "generate_reply", return_value="대운과 세운을 같이 보면 시점이 조금 더 선명할 수 있습니다."), \
                 mock.patch.object(g, "publish_reply", side_effect=g.APIError("definite reject")):
                result = g.run_growth(
                    object(), self.cfg, self.state,
                    {"read_replies": False, "keyword_search": True, "profile_posts": False, "token_scopes": []},
                    send=True, do_external=True, do_inbound=False,
                )
            self.assertEqual(result["day"]["external"], 0)
            self.assertEqual(result["day"]["total"], 0)
            self.assertEqual(len(self.state["sent"]), 0)
            self.assertTrue(g.can_send_external(self.cfg, self.state, "writer-fail"))
        finally:
            marker.unlink(missing_ok=True)

    def test_existing_pending_send_hard_holds_new_live_run(self):
        candidate = g.Candidate(id="pending-target", username="pending-user", text="재물운 질문", timestamp=g.utcnow().isoformat(), kind="external")
        g.reserve_send(self.state, candidate, "맥락 있는 답변입니다.", persist=False)
        with mock.patch.object(g, "publish_reply") as publish:
            result = g.run_growth(
                object(), self.cfg, self.state,
                {"read_replies": False, "keyword_search": True, "profile_posts": False, "token_scopes": []},
                send=True, do_external=True, do_inbound=False,
            )
        publish.assert_not_called()
        self.assertFalse(result["send"])
        self.assertEqual(result["hold_reason"], "pending_send_requires_reconcile")

    def test_external_text_is_revalidated_at_publish_boundary(self):
        candidate = g.Candidate(
            id="ex-promo-boundary", username="promo-user", text="사주 재물운 질문입니다. 궁금해요.",
            timestamp=g.utcnow().isoformat(), kind="external", score=100,
        )
        with mock.patch.object(g, "external_candidates", return_value=[candidate]), \
             mock.patch.object(g, "generate_reply", return_value="현담 앱을 설치해 보세요. 할인 이벤트 진행 중입니다."), \
             mock.patch.object(g, "publish_reply") as publish:
            result = g.run_growth(
                object(), self.cfg, self.state,
                {"read_replies": False, "keyword_search": True, "profile_posts": False, "token_scopes": []},
                send=True, do_external=True, do_inbound=False,
            )
        publish.assert_not_called()
        self.assertEqual(result["day"]["external"], 0)


class ExternalWriterLockTests(unittest.TestCase):
    def test_writer_lock_rejects_parallel_writer(self):
        lock_path = _test_path("_test_threads_growth.lock")
        lock_path.unlink(missing_ok=True)
        try:
            with g.writer_lock(lock_path):
                with self.assertRaises(g.WriterLockBusy):
                    with g.writer_lock(lock_path):
                        pass
        finally:
            lock_path.unlink(missing_ok=True)


class FinalAuditRegressionTests(unittest.TestCase):
    def setUp(self):
        g.PAUSE_PATH.unlink(missing_ok=True)
        g.STATE_PATH.unlink(missing_ok=True)
        self.cfg = dict(g.load_config())
        self.state = g.default_state()

    def tearDown(self):
        g.PAUSE_PATH.unlink(missing_ok=True)
        g.STATE_PATH.unlink(missing_ok=True)

    def test_unknown_receipt_hard_holds_future_live_send(self):
        self.state["sent"].append({
            "kind": "external", "target_id": "unknown-target", "target_username": "u",
            "effect": "UNKNOWN", "date_kst": g.date_key(), "text": "과거 불확실 발송",
        })
        result = g.run_growth(
            object(), self.cfg, self.state,
            {"read_replies": False, "keyword_search": False, "profile_posts": False, "token_scopes": []},
            send=True, do_external=False, do_inbound=False,
        )
        self.assertFalse(result["send"])
        self.assertEqual(result["hold_reason"], "unresolved_send_requires_reconcile")
        self.assertEqual(len(g.unresolved_sends(self.state)), 1)

    def test_state_file_with_only_schema_is_corrupt_not_migrated_empty(self):
        g.STATE_PATH.write_text('{"schema": 1}', encoding="utf-8")
        with self.assertRaises(g.StateCorruption):
            g.load_state()

    def test_state_rejects_invalid_nested_counters(self):
        bad = g.default_state()
        bad["days"] = {g.date_key(): {"external": -1, "inbound": 0, "nested": 0, "total": 0, "per_target": {}}}
        g.STATE_PATH.write_text(__import__('json').dumps(bad), encoding="utf-8")
        with self.assertRaises(g.StateCorruption):
            g.load_state()

    def test_pause_created_during_target_preflight_blocks_post(self):
        class API:
            def __init__(self): self.post_calls = 0
            def get(self, path, params=None):
                if path == "target-boundary":
                    g.PAUSE_PATH.write_text('{"reason":"mid_preflight"}', encoding="utf-8")
                    return {"id": "target-boundary"}
                return {"data": []}
            def post(self, path, data=None):
                self.post_calls += 1
                return {"id": "must-not-post"}
        api = API()
        c = g.Candidate(id="target-boundary", username="u", text="재물운 질문", timestamp=g.utcnow().isoformat(), kind="external")
        with self.assertRaises(g.PublishHeld):
            g.publish_reply(api, c, "대운과 세운을 같이 보면 시점이 선명해질 수 있어요.")
        self.assertEqual(api.post_calls, 0)

    def test_post_http_500_is_uncertain_not_definite_failure(self):
        class API:
            def get(self, path, params=None): return {"id": "target-500"}
            def post(self, path, data=None): raise g.APIError("server error", status=500)
        c = g.Candidate(id="target-500", username="u", text="재물운 질문", timestamp=g.utcnow().isoformat(), kind="external")
        with self.assertRaises(g.UncertainPublish):
            g.publish_reply(API(), c, "대운과 세운을 같이 보면 시점이 선명해질 수 있어요.")
        self.assertTrue(g.PAUSE_PATH.exists())

    def test_post_nonjson_200_style_error_is_uncertain(self):
        class API:
            def get(self, path, params=None): return {"id": "target-200"}
            def post(self, path, data=None): raise g.APIError("non-json response", status=200)
        c = g.Candidate(id="target-200", username="u", text="재물운 질문", timestamp=g.utcnow().isoformat(), kind="external")
        with self.assertRaises(g.UncertainPublish):
            g.publish_reply(API(), c, "대운과 세운을 같이 보면 시점이 선명해질 수 있어요.")
        self.assertTrue(g.PAUSE_PATH.exists())

    def test_post_http_400_is_definite_rejection(self):
        class API:
            def get(self, path, params=None): return {"id": "target-400"}
            def post(self, path, data=None): raise g.APIError("bad request", status=400, response_json_valid=True)
        c = g.Candidate(id="target-400", username="u", text="재물운 질문", timestamp=g.utcnow().isoformat(), kind="external")
        with self.assertRaises(g.APIError):
            g.publish_reply(API(), c, "대운과 세운을 같이 보면 시점이 선명해질 수 있어요.")
        self.assertFalse(g.PAUSE_PATH.exists())

    def test_partial_insights_payload_is_failure(self):
        class API:
            def get(self, path, params=None):
                return {"data": [
                    {"name": "views", "values": [{"value": 10}]},
                    {"name": "likes", "values": [{"value": 1}]},
                ]}
        cfg = dict(self.cfg)
        cfg["external_insights_min_age_hours"] = 0
        cfg["external_insights_refresh_hours"] = 0
        now = g.utcnow()
        c = g.Candidate(id="t-partial", username="u", text="재물운 질문", timestamp=now.isoformat(), kind="external")
        g.record_send(self.state, c, "맥락 있는 답변입니다.", {"id":"r-partial","replied_to":{"id":"t-partial"}}, dry_run=False, now=now-dt.timedelta(hours=3))
        result = g.collect_external_insights(API(), cfg, self.state, now=now)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["measured"], 0)

    def test_malformed_required_metric_is_failure(self):
        class API:
            def get(self, path, params=None):
                return {"data": [
                    {"name": "views", "values": [{"value": "not-a-number"}]},
                    {"name": "likes", "values": [{"value": 1}]},
                    {"name": "replies", "values": [{"value": 0}]},
                ]}
        cfg = dict(self.cfg)
        cfg["external_insights_min_age_hours"] = 0
        cfg["external_insights_refresh_hours"] = 0
        now = g.utcnow()
        c = g.Candidate(id="t-mal", username="u2", text="대운 질문", timestamp=now.isoformat(), kind="external")
        g.record_send(self.state, c, "맥락 있는 답변입니다.", {"id":"r-mal","replied_to":{"id":"t-mal"}}, dry_run=False, now=now-dt.timedelta(hours=3))
        result = g.collect_external_insights(API(), cfg, self.state, now=now)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["measured"], 0)

    def test_lost_insights_scope_blocks_stage_promotion(self):
        cfg = dict(self.cfg)
        cfg.update({
            "external_growth_stage_days": 7,
            "external_growth_min_stage_sends": 7,
            "external_growth_min_measured": 7,
            "external_growth_min_engagement_rate": 0.0,
            "external_growth_max_error_rate": 0.0,
            "external_growth_max_insight_failure_rate": 0.0,
        })
        now = dt.datetime(2026, 10, 20, 3, 0, tzinfo=dt.timezone.utc)
        self.state["external_growth"] = {"stage_index": 0, "stage_started_kst": "2026-10-13", "history": []}
        for day in range(13, 20):
            self.state["days"][f"2026-10-{day:02d}"] = {
                "external": 1, "inbound": 0, "nested": 0, "total": 1, "per_target": {},
                "external_measured": 1, "external_engaged": 1, "external_errors": 0,
                "external_safety_stops": 0, "external_insight_failures": 0,
            }
        result = g.maybe_advance_external_stage(cfg, self.state, now, telemetry_available=False)
        self.assertFalse(result["promoted"])
        self.assertEqual(result["daily_cap"], 8)
        self.assertFalse(result["telemetry_available"])

    def test_unresolved_receipt_blocks_stage_promotion(self):
        cfg = dict(self.cfg)
        cfg.update({
            "external_growth_stage_days": 7,
            "external_growth_min_stage_sends": 7,
            "external_growth_min_measured": 7,
            "external_growth_min_engagement_rate": 0.0,
            "external_growth_max_error_rate": 0.0,
            "external_growth_max_insight_failure_rate": 0.0,
        })
        now = dt.datetime(2026, 10, 20, 3, 0, tzinfo=dt.timezone.utc)
        self.state["external_growth"] = {"stage_index": 0, "stage_started_kst": "2026-10-13", "history": []}
        for day in range(13, 20):
            self.state["days"][f"2026-10-{day:02d}"] = {
                "external": 1, "inbound": 0, "nested": 0, "total": 1, "per_target": {},
                "external_measured": 1, "external_engaged": 1, "external_errors": 0,
                "external_safety_stops": 0, "external_insight_failures": 0,
            }
        self.state["sent"].append({"effect":"UNKNOWN", "kind":"external", "target_id":"x"})
        result = g.maybe_advance_external_stage(cfg, self.state, now, telemetry_available=True)
        self.assertFalse(result["promoted"])
        self.assertGreater(result["unresolved"], 0)

    def test_save_json_fsyncs_before_replace(self):
        target = g.STATE_PATH.parent / "durable.json"
        with mock.patch.object(g.os, "fsync", wraps=g.os.fsync) as fsync:
            g.save_json(target, {"ok": True})
        self.assertGreaterEqual(fsync.call_count, 1)
        self.assertEqual(__import__('json').loads(target.read_text(encoding="utf-8")), {"ok": True})

    def test_dm_solicitation_is_blocked_for_external_reply(self):
        ok, _ = g.quality_gate("자세한 풀이가 필요하면 DM 주세요", self.cfg, self.state, external=True)
        self.assertFalse(ok)

    def test_main_acquires_writer_lock_before_loading_live_state(self):
        events = []
        class Lock:
            def __enter__(self): events.append("lock_enter"); return self
            def __exit__(self, *args): events.append("lock_exit")
        def fake_load_state():
            events.append("load_state")
            return g.default_state()
        def fake_run(*args, **kwargs):
            events.append("run_growth")
            return {
                "date_kst": g.date_key(), "send": True, "day": g.today_bucket(g.default_state()),
                "actions": [], "paused": False, "external_growth": {}, "external_insights": {}, "hold_reason": ""
            }
        with mock.patch.object(g, "writer_lock", return_value=Lock()), \
             mock.patch.object(g, "load_state", side_effect=fake_load_state), \
             mock.patch.object(g, "ThreadsAPI", return_value=object()), \
             mock.patch.object(g, "api_capabilities", return_value={"basic": True}), \
             mock.patch.object(g, "run_growth", side_effect=fake_run), \
             mock.patch.object(g, "write_report"), \
             mock.patch.object(g.sys, "argv", ["threads_growth.py", "--send", "--no-external", "--no-inbound"]), \
             mock.patch.dict(g.os.environ, {"THREADS_ACCESS_TOKEN":"t", "THREADS_USER_ID":"u"}, clear=False):
            rc = g.main()
        self.assertEqual(rc, 0)
        self.assertLess(events.index("lock_enter"), events.index("load_state"))
        self.assertLess(events.index("load_state"), events.index("run_growth"))
        self.assertLess(events.index("run_growth"), events.index("lock_exit"))


class FinalAuditRound2Tests(unittest.TestCase):
    def setUp(self):
        g.PAUSE_PATH.unlink(missing_ok=True)
        g.STATE_PATH.unlink(missing_ok=True)
        self.cfg = dict(g.load_config())
        self.state = g.default_state()

    def tearDown(self):
        g.PAUSE_PATH.unlink(missing_ok=True)
        g.STATE_PATH.unlink(missing_ok=True)

    def test_existing_day_bucket_missing_core_quota_field_is_corrupt(self):
        state = g.default_state()
        state["days"] = {g.date_key(): {"external": 1, "inbound": 0, "nested": 0, "per_target": {"u": 1}}}
        g.STATE_PATH.write_text(__import__('json').dumps(state), encoding="utf-8")
        with self.assertRaises(g.StateCorruption):
            g.load_state()

    def test_legacy_day_bucket_may_lack_only_new_telemetry_fields(self):
        state = g.default_state()
        state["days"] = {g.date_key(): {"external": 1, "inbound": 0, "nested": 0, "total": 1, "per_target": {"u": 1}}}
        g.STATE_PATH.write_text(__import__('json').dumps(state), encoding="utf-8")
        loaded = g.load_state()
        bucket = g.today_bucket(loaded)
        self.assertEqual(bucket["total"], 1)
        self.assertEqual(bucket["external"], 1)
        self.assertEqual(bucket["per_target"]["u"], 1)
        self.assertEqual(bucket["external_measured"], 0)

    def test_nonjson_http_400_post_is_uncertain(self):
        class API:
            def get(self, path, params=None): return {"id": "t400-nonjson"}
            def post(self, path, data=None):
                raise g.APIError("HTTP 400: non-json response", status=400, response_json_valid=False)
        c = g.Candidate(id="t400-nonjson", username="u", text="재물운 질문", timestamp=g.utcnow().isoformat(), kind="external")
        with self.assertRaises(g.UncertainPublish):
            g.publish_reply(API(), c, "대운과 세운을 같이 보면 시점이 선명해질 수 있어요.")
        self.assertTrue(g.PAUSE_PATH.exists())

    def test_json_http_400_post_is_definite_rejection(self):
        class API:
            def get(self, path, params=None): return {"id": "t400-json"}
            def post(self, path, data=None):
                raise g.APIError("bad request", status=400, response_json_valid=True)
        c = g.Candidate(id="t400-json", username="u", text="재물운 질문", timestamp=g.utcnow().isoformat(), kind="external")
        with self.assertRaises(g.APIError):
            g.publish_reply(API(), c, "대운과 세운을 같이 보면 시점이 선명해질 수 있어요.")
        self.assertFalse(g.PAUSE_PATH.exists())

    def test_directory_fsync_failure_propagates(self):
        target = g.STATE_PATH.parent / "durability-failure.json"
        real_fsync = g.os.fsync
        calls = {"n": 0}
        def fail_second(fd):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("directory fsync failed")
            return real_fsync(fd)
        with mock.patch.object(g.os, "fsync", side_effect=fail_second):
            with self.assertRaises(OSError):
                g.save_json(target, {"ok": True})

    def test_inbound_scan_failure_sets_scheduler_hold(self):
        with mock.patch.object(g, "inbound_candidates", side_effect=g.CandidateScanError("inbound down")):
            result = g.run_growth(
                object(), self.cfg, self.state,
                {"read_replies": True, "keyword_search": False, "profile_posts": False, "token_scopes": []},
                send=True, do_external=False, do_inbound=True,
            )
        self.assertEqual(result["hold_reason"], "inbound_scan_error")

    def test_external_scan_failure_sets_scheduler_hold(self):
        with mock.patch.object(g, "external_candidates", side_effect=g.CandidateScanError("external down")):
            result = g.run_growth(
                object(), self.cfg, self.state,
                {"read_replies": False, "keyword_search": True, "profile_posts": False, "token_scopes": []},
                send=True, do_external=True, do_inbound=False,
            )
        self.assertEqual(result["hold_reason"], "external_scan_error")


class ExternalSelfAccountExclusionTests(unittest.TestCase):
    def test_keyword_discovery_never_targets_own_account(self):
        cfg = dict(g.load_config())
        cfg["topic_keywords"] = ["사주"]
        cfg["keyword_search_types"] = ["RECENT"]
        cfg["keyword_discovery_enabled"] = True
        cfg["keyword_discovery_min_relevance"] = 1
        state = g.default_state()

        class API:
            def get(self, path, params=None):
                self.assert_path = path
                return {"data": [
                    {
                        "id": "own-post",
                        "username": cfg["account_username"],
                        "text": "사주 십성과 재물운은 어떻게 같이 보시나요? 궁금합니다.",
                        "timestamp": g.utcnow().isoformat(),
                        "permalink": "https://example.invalid/own",
                        "is_reply": False,
                        "has_replies": True,
                    },
                    {
                        "id": "other-post",
                        "username": "other_reader",
                        "text": "사주 십성과 재물운은 어떻게 같이 보시나요? 궁금합니다.",
                        "timestamp": g.utcnow().isoformat(),
                        "permalink": "https://example.invalid/other",
                        "is_reply": False,
                        "has_replies": True,
                    },
                ]}

        rows = g.external_candidates(API(), cfg, state, {"profile_posts": False, "keyword_search": True})
        self.assertNotIn(cfg["account_username"].lower(), {x.username.lower() for x in rows})
        self.assertIn("other_reader", {x.username for x in rows})

    def test_keyword_discovery_normalizes_at_case_and_spaces_for_self_exclusion(self):
        cfg = dict(g.load_config())
        cfg["account_username"] = " @GSDO10042026 "
        cfg["topic_keywords"] = ["사주"]
        cfg["keyword_search_types"] = ["RECENT"]
        cfg["keyword_discovery_enabled"] = True
        cfg["keyword_discovery_min_relevance"] = 1
        state = g.default_state()

        class API:
            def get(self, path, params=None):
                return {"data": [
                    {"id": "own-post", "username": "gsdo10042026", "text": "사주 재물운과 대운 흐름은 실제로 어떤 순서로 함께 보시나요? 정말 궁금합니다.", "timestamp": g.utcnow().isoformat(), "is_reply": False},
                    {"id": "other-post", "username": "Other_Reader", "text": "사주 재물운과 대운 흐름은 실제로 어떤 순서로 함께 보시나요? 정말 궁금합니다.", "timestamp": g.utcnow().isoformat(), "is_reply": False},
                ]}

        rows = g.external_candidates(API(), cfg, state, {"profile_posts": False, "keyword_search": True})
        self.assertEqual({x.username for x in rows}, {"Other_Reader"})

    def test_profile_discovery_excludes_self_and_keeps_other(self):
        cfg = dict(g.load_config())
        cfg["account_username"] = "@GSDO10042026"
        cfg["target_accounts"] = [" @gsdo10042026 ", "other_profile"]
        state = g.default_state()
        called = []

        class API:
            def get(self, path, params=None):
                called.append(params.get("username"))
                return {"data": [
                    {"id": "self-via-profile", "username": " GSDO10042026 ", "text": "사주 재물운과 대운 흐름에 대해 질문합니다. 실제 해석은 어떤 순서로 보시나요?", "timestamp": g.utcnow().isoformat(), "is_reply": False},
                    {"id": "other-via-profile", "username": "other_profile", "text": "사주 재물운과 대운 흐름에 대해 질문합니다. 실제 해석은 어떤 순서로 보시나요?", "timestamp": g.utcnow().isoformat(), "is_reply": False},
                ]}

        rows = g.external_candidates(API(), cfg, state, {"profile_posts": True, "keyword_search": False})
        self.assertEqual(called, ["other_profile"])
        self.assertEqual({x.username for x in rows}, {"other_profile"})


if __name__ == "__main__":
    unittest.main()
