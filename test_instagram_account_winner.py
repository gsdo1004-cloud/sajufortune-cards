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
        "samples": [{"collected_at": "2026-10-20T00:00:00+00:00", "metrics": {"views": 999}}],
    }
    assert iaw.sample_near_age(entry, 24, tolerance_hours=30) is None
