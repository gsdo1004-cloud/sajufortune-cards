import json

import pytest

import zodiac_instagram as zi


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.content = b"{}"

    def json(self):
        return self._data


def test_primary_marker_keeps_legacy_filename_for_backward_compat(monkeypatch, tmp_path):
    monkeypatch.setattr(zi, "BASE", tmp_path)
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_KEY", raising=False)
    assert zi._marker("2026-10-14", "reel").name == "instagram_pub_reel.json"


def test_second_account_marker_is_account_scoped(monkeypatch, tmp_path):
    monkeypatch.setattr(zi, "BASE", tmp_path)
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_KEY", "sajufortune.kr")
    assert zi._marker("2026-10-14", "reel").name == "instagram_pub_reel_sajufortune_kr.json"


def test_marker_records_account_and_variant(monkeypatch, tmp_path):
    monkeypatch.setattr(zi, "BASE", tmp_path)
    monkeypatch.setenv("INSTAGRAM_ACCOUNT_KEY", "sajufortune.kr")
    monkeypatch.setenv("INSTAGRAM_EXPERIMENT_VARIANT", "B")
    zi._write_marker("2026-10-14", "reel", "123", media_url="https://example.test/r.mp4")
    payload = json.loads(zi._marker("2026-10-14", "reel").read_text(encoding="utf-8"))
    assert payload["account_key"] == "sajufortune.kr"
    assert payload["experiment_variant"] == "B"


def test_preflight_fails_closed_on_wrong_account(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_USER_ID", "1")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "token")
    monkeypatch.setenv("INSTAGRAM_EXPECTED_USERNAME", "sajufortune.kr")
    monkeypatch.setattr(zi.requests, "get", lambda *a, **k: FakeResponse({
        "id": "1", "username": "gsdo10042026", "account_type": "BUSINESS", "media_count": 10
    }))
    with pytest.raises(RuntimeError, match="account mismatch"):
        zi.preflight()


def test_caption_variant_changes_intro_without_changing_topic(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_EXPERIMENT_VARIANT", "A")
    a = zi.reel_caption("2026-10-14")
    monkeypatch.setenv("INSTAGRAM_EXPERIMENT_VARIANT", "B")
    b = zi.reel_caption("2026-10-14")
    assert a != b
    assert "띠별 운세" in a
    assert "띠별 운세" in b
    assert "#띠별운세" in a and "#띠별운세" in b


def test_reel_media_url_uses_video_variant(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_EXPERIMENT_VARIANT", "B")
    assert zi.reel_media_url("2026-10-14").endswith("/reels/2026-10-14_tts_ig_B.mp4")
