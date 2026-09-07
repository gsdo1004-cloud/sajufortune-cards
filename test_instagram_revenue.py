from pathlib import Path
import json
import zodiac_instagram as zi


def test_profile_landing_is_attributed():
    assert "utm_source=instagram" in zi.PROFILE_LANDING
    assert "utm_medium=profile" in zi.PROFILE_LANDING
    assert "instagram_reels_revenue" in zi.PROFILE_LANDING


def test_auto_comment_defaults_off(monkeypatch):
    assert zi.AUTO_COMMENT is False


def test_marker_prevents_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(zi, "BASE", tmp_path)
    p=zi._marker("2026-09-07","reel")
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"post_id":"x"}),encoding="utf-8")
    assert zi._skip_if_done("2026-09-07","reel") is True


def test_target_modes_present():
    src=Path(zi.__file__).read_text(encoding="utf-8")
    assert 'mode == "reel"' in src
    assert 'mode == "signal"' in src
    assert 'mode == "carousel"' in src
