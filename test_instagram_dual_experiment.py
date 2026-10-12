import pytest

import instagram_dual_experiment as ide


def test_crossed_assignment_swaps_account_slots_and_variants():
    d1 = ide.plan_for_date("2026-10-14")
    d2 = ide.plan_for_date("2026-10-15")
    assert {x["account_key"] for x in d1["assignments"]} == {"gsdo10042026", "sajufortune.kr"}
    assert {x["slot"] for x in d1["assignments"]} == {"early", "late"}
    assert {x["variant"] for x in d1["assignments"]} == {"A", "B"}
    by_account_1 = {x["account_key"]: x for x in d1["assignments"]}
    by_account_2 = {x["account_key"]: x for x in d2["assignments"]}
    assert by_account_1["gsdo10042026"]["slot"] != by_account_2["gsdo10042026"]["slot"]
    assert by_account_1["gsdo10042026"]["variant"] != by_account_2["gsdo10042026"]["variant"]


def test_assignment_for_slot_is_deterministic():
    p = ide.assignment_for_slot("2026-10-14", "early")
    assert p == ide.assignment_for_slot("2026-10-14", "early")
    assert p["account_key"] in {"gsdo10042026", "sajufortune.kr"}
    assert p["variant"] in {"A", "B"}


def test_marker_key_is_filesystem_safe_and_distinct():
    assert ide.marker_key("gsdo10042026") == "gsdo10042026"
    assert ide.marker_key("sajufortune.kr") == "sajufortune_kr"
    assert ide.marker_key("gsdo10042026") != ide.marker_key("sajufortune.kr")


def test_winner_waits_for_minimum_samples():
    samples = {"gsdo10042026": [{"views": 1000}] * 19, "sajufortune.kr": [{"views": 2000}] * 19}
    result = ide.choose_winner(samples, min_samples=20)
    assert result["status"] == "collecting"
    assert result["winner"] is None


def test_winner_uses_median_views_and_engagement_not_single_viral_outlier():
    current = [{"views": 1000, "reach": 900, "shares": 10, "saved": 8, "total_interactions": 40}] * 20
    legacy = [{"views": 1600, "reach": 1400, "shares": 20, "saved": 12, "total_interactions": 70}] * 19
    legacy.append({"views": 50000, "reach": 40000, "shares": 300, "saved": 200, "total_interactions": 900})
    result = ide.choose_winner({"gsdo10042026": current, "sajufortune.kr": legacy}, min_samples=20)
    assert result["status"] == "ready"
    assert result["winner"] == "sajufortune.kr"
    assert result["accounts"]["sajufortune.kr"]["median_views"] == 1600


def test_unknown_slot_rejected():
    with pytest.raises(ValueError):
        ide.assignment_for_slot("2026-10-14", "nope")
