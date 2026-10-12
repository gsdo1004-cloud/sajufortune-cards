import datetime as dt

import instagram_account_winner as iaw


def test_sample_near_age_selects_closest_post_target_sample():
    entry = {
        "timestamp": "2026-10-14T00:00:00+00:00",
        "samples": [
            {"collected_at": "2026-10-14T20:00:00+00:00", "metrics": {"views": 100}},
            {"collected_at": "2026-10-15T01:00:00+00:00", "metrics": {"views": 140}},
            {"collected_at": "2026-10-17T02:00:00+00:00", "metrics": {"views": 400}},
        ],
    }
    s24 = iaw.sample_near_age(entry, 24)
    s72 = iaw.sample_near_age(entry, 72)
    assert s24["views"] == 140
    assert s72["views"] == 400


def test_sample_near_age_rejects_samples_too_far_after_window():
    entry = {
        "timestamp": "2026-10-14T00:00:00+00:00",
        "samples": [
            {"collected_at": "2026-10-20T00:00:00+00:00", "metrics": {"views": 999}},
        ],
    }
    assert iaw.sample_near_age(entry, 24, tolerance_hours=30) is None


def test_marker_ids_only_counts_new_experiment_markers(tmp_path):
    import json
    d = tmp_path / "cards" / "2026-10-14"
    d.mkdir(parents=True)
    (d / "instagram_pub_reel.json").write_text(json.dumps({"post_id": "old-primary"}), encoding="utf-8")
    (d / "instagram_pub_reel_sajufortune_kr.json").write_text(json.dumps({
        "post_id": "new-legacy", "account_key": "sajufortune.kr", "experiment_variant": "B"
    }), encoding="utf-8")
    assert iaw.marker_ids(tmp_path, "gsdo10042026") == set()
    assert iaw.marker_ids(tmp_path, "sajufortune.kr") == {"new-legacy"}
