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
    fake=tmp_path/"zodiac_reels.py"
    fake.write_text("")
    with patch.object(zr,"__file__",str(fake)),          patch.object(zr,"publish_video",return_value="post123"),          patch.object(zr,"publish_reply",side_effect=RuntimeError("optional")):
        zr.do_publish("2026-11-23")
    receipt=tmp_path/"cards"/"2026-11-23"/"threads_pub_reels.json"
    assert receipt.is_file()
    assert "post123" in receipt.read_text()
