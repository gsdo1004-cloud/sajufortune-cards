"""Threads video integrity regression; no real API calls or new posts."""
import os
from unittest.mock import MagicMock, patch
import pytest
import zodiac_reels as zr
import media_preflight


def test_remote_media_404_never_calls_meta():
    with patch.object(media_preflight,"check_public_media",return_value=(False,"HTTP 404")),          patch.object(zr,"_post") as posting:
        with pytest.raises(RuntimeError,match="media invalid"):
            zr.publish_video("https://example.org/missing.mp4","caption")
        posting.assert_not_called()


def test_processing_not_finished_prevents_publish():
    with patch.object(media_preflight,"check_public_media",return_value=(True,"ok")),          patch.dict(os.environ,{"THREADS_ACCESS_TOKEN":"test"}),          patch("zodiac_cardnews._threads_uid",return_value="uid"),          patch.object(zr,"_post",return_value={"id":"container"}) as posting,          patch.object(zr.time,"sleep"),          patch("requests.get",return_value=MagicMock(json=lambda:{"status":"IN_PROGRESS"})):
        with pytest.raises(RuntimeError,match="not FINISHED"):
            zr.publish_video("https://example.org/ok.mp4","caption")
        assert posting.call_count==1


def test_finished_publishes_once():
    with patch.object(media_preflight,"check_public_media",return_value=(True,"ok")),          patch.dict(os.environ,{"THREADS_ACCESS_TOKEN":"test"}),          patch("zodiac_cardnews._threads_uid",return_value="uid"),          patch.object(zr,"_post",side_effect=[{"id":"container"},{"id":"post"}]) as posting,          patch.object(zr.time,"sleep"),          patch("requests.get",return_value=MagicMock(json=lambda:{"status":"FINISHED"})):
        assert zr.publish_video("https://example.org/ok.mp4","caption")=="post"
        assert posting.call_count==2


def test_comment_failure_keeps_published_receipt(tmp_path):
    day = "2026-10-21"  # historical PNG content, before signed-release cutover
    fake = tmp_path / "zodiac_reels.py"
    fake.write_text("")
    cards = tmp_path / "cards" / day
    cards.mkdir(parents=True)
    (cards / "card_01.png").write_bytes(b"legacy fixture")
    with patch.object(zr, "__file__", str(fake)), patch.object(zr, "BASE", tmp_path), \
         patch.object(zr, "publish_video", return_value="post123") as publish, \
         patch.object(zr, "publish_reply", side_effect=RuntimeError("optional")):
        zr.do_publish(day)
        zr.do_publish(day)  # persisted receipt must prevent a duplicate
        publish.assert_called_once()
    receipt = cards / "threads_pub_reels.json"
    assert receipt.is_file()
    assert "post123" in receipt.read_text()


def test_new_unsigned_video_cannot_publish_or_write_receipt(tmp_path):
    from scripts.zodiac_publish_guard import ReleaseHold
    day = "2026-11-23"
    reels = tmp_path / "reels"
    reels.mkdir()
    (reels / f"{day}_tts.mp4").write_bytes(b"unapproved fixture")
    with patch.object(zr, "__file__", str(tmp_path / "zodiac_reels.py")), \
         patch.object(zr, "BASE", tmp_path), patch.object(zr, "publish_video") as publish, \
         patch.object(zr, "publish_reply") as reply:
        with pytest.raises(ReleaseHold, match="RELEASE_STYLED_ASSETS_WITHOUT_MANIFEST"):
            zr.do_publish(day)
        publish.assert_not_called()
        reply.assert_not_called()
    assert not (tmp_path / "cards" / day / "threads_pub_reels.json").exists()


def test_signed_video_remote_sha_failure_prevents_post_and_receipt(tmp_path):
    from scripts import zodiac_publish_guard as guard
    day = "2026-12-07"
    with patch.object(zr, "__file__", str(tmp_path / "zodiac_reels.py")), \
         patch.object(zr, "BASE", tmp_path), \
         patch.object(guard, "check", return_value={"status": "VERIFIED_SIGNED_RELEASE", "video_sha256": "a" * 64}), \
         patch.dict(os.environ, {"ZODIAC_RAW_COMMIT_SHA": "b" * 40}), \
         patch.object(guard, "verify_remote_sha", side_effect=guard.ReleaseHold("remote SHA mismatch")) as verify, \
         patch.object(zr, "publish_video") as publish, patch.object(zr, "publish_reply") as reply:
        with pytest.raises(guard.ReleaseHold, match="remote SHA mismatch"):
            zr.do_publish(day)
        verify.assert_called_once_with(f"https://raw.githubusercontent.com/gsdo1004-cloud/sajufortune-cards/{'b' * 40}/reels/{day}_tts.mp4", "a" * 64, require_immutable=True)
        publish.assert_not_called()
        reply.assert_not_called()
    assert not (tmp_path / "cards" / day / "threads_pub_reels.json").exists()
