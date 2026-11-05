# -*- coding: utf-8 -*-
"""Safe regression tests: no real Meta or publishing API calls."""
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import media_preflight
import zodiac_cardnews
import zodiac_instagram


class FakeResponse:
    def __init__(self, status=200, payload=b"", content_type="application/octet-stream", size=4096):
        self.status_code = status
        self.headers = {"content-type": content_type, "content-length": str(size)}
        self.payload = payload
        self.closed = False

    def iter_content(self, chunk_size=32):
        yield self.payload[:chunk_size]

    def close(self):
        self.closed = True


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 768, 1360) + b"\x00" * 8
MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 24


class MediaPreflightTests(unittest.TestCase):
    @patch.object(media_preflight.requests, "get")
    def test_image_png_checked(self, get):
        get.return_value = FakeResponse(payload=PNG, content_type="image/png")
        ok, detail = media_preflight.check_public_media("https://example.org/card.png", "image")
        self.assertTrue(ok, detail)
        self.assertIn("768x1360", detail)
        self.assertTrue(get.return_value.closed)

    @patch.object(media_preflight.requests, "get")
    def test_missing_asset_is_held(self, get):
        get.return_value = FakeResponse(status=404)
        ok, detail = media_preflight.check_public_media("https://example.org/missing.png", "image")
        self.assertFalse(ok)
        self.assertEqual(detail, "HTTP 404")

    @patch.object(media_preflight.requests, "get")
    def test_html_and_invalid_image_rejected(self, get):
        get.return_value = FakeResponse(payload=b"<html>", content_type="text/html")
        self.assertFalse(media_preflight.check_public_media("https://example.org/card.png", "image")[0])
        get.return_value = FakeResponse(payload=b"not an image", content_type="image/png")
        self.assertFalse(media_preflight.check_public_media("https://example.org/card.png", "image")[0])

    @patch.object(media_preflight.requests, "get")
    def test_oversized_asset_is_held(self, get):
        get.return_value = FakeResponse(payload=PNG, size=media_preflight._IMAGE_LIMIT + 1)
        ok, detail = media_preflight.check_public_media("https://example.org/card.png", "image")
        self.assertFalse(ok)
        self.assertIn("out-of-range", detail)

    @patch.object(media_preflight.requests, "get")
    def test_mp4_header_and_ffprobe_gate(self, get):
        get.return_value = FakeResponse(payload=MP4)
        with patch.object(media_preflight, "_probe_video", return_value=(True, "codec=h264")):
            self.assertTrue(media_preflight.check_public_media("https://example.org/a.mp4", "video")[0])
        with patch.object(media_preflight, "_probe_video", return_value=(False, "unsupported codec")):
            self.assertFalse(media_preflight.check_public_media("https://example.org/a.mp4", "video")[0])
        get.return_value = FakeResponse(payload=b"<html>" * 5)
        with patch.object(media_preflight, "_probe_video") as probe:
            self.assertFalse(media_preflight.check_public_media("https://example.org/a.mp4", "video")[0])
            probe.assert_not_called()

    @patch.object(media_preflight.shutil, "which", return_value="/usr/bin/ffprobe")
    @patch.object(media_preflight.subprocess, "run")
    def test_ffprobe_detects_unsupported_video(self, run, which):
        run.return_value = MagicMock(returncode=0, stdout='{"streams":[{"codec_type":"video","codec_name":"vp9","width":1080,"height":1920}],"format":{"duration":"30"}}')
        with patch.dict(os.environ, {"MEDIA_PREFLIGHT_FFPROBE": "1"}):
            ok, detail = media_preflight._probe_video("https://example.org/a.mp4")
        self.assertFalse(ok)
        self.assertIn("unsupported", detail)


class ThreadsGuardTests(unittest.TestCase):
    def test_does_not_create_containers_if_any_asset_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            carddir = Path(d) / "cards" / "2026-11-05"
            carddir.mkdir(parents=True)
            for n in (1, 2):
                (carddir / f"card_{n:02d}.png").write_bytes(PNG)
            with patch.object(zodiac_cardnews, "__file__", str(Path(d) / "zodiac_cardnews.py")), \
                 patch.object(zodiac_cardnews, "check_public_media", side_effect=[(True, "valid"), (False, "HTTP 404")]), \
                 patch.object(zodiac_cardnews, "_post") as posting:
                with self.assertRaises(SystemExit):
                    zodiac_cardnews._verified_image_urls("2026-11-05")
                posting.assert_not_called()

    @patch.object(zodiac_cardnews.time, "sleep")
    @patch.object(zodiac_cardnews, "check_public_media", return_value=(True, "ready"))
    @patch.object(zodiac_cardnews, "_threads_uid", return_value="owned-user")
    @patch.object(zodiac_cardnews, "_post")
    def test_retries_only_media_fetch_not_final_publish(self, post, uid, check, sleep):
        error = {"error": {"code": 1, "error_subcode": 2207052}}
        post.side_effect = [error, {"id": "child"}, {"id": "car"}, {"id": "post"}]
        with patch.dict(os.environ, {"THREADS_ACCESS_TOKEN": "dummy"}):
            pid = zodiac_cardnews.publish_carousel(["https://example.org/a.png"], "text", "2026-11-05")
        self.assertEqual(pid, "post")
        self.assertEqual(post.call_count, 4)
        check.assert_called_once()
        publish_calls = [c for c in post.call_args_list if "threads_publish" in c.args[0]]
        self.assertEqual(len(publish_calls), 1)

    @patch.object(zodiac_cardnews.time, "sleep")
    @patch.object(zodiac_cardnews, "_threads_uid", return_value="owned-user")
    @patch.object(zodiac_cardnews, "_post", return_value={"error": {"code": 190}})
    def test_non_media_error_is_never_retried(self, post, uid, sleep):
        with patch.dict(os.environ, {"THREADS_ACCESS_TOKEN": "dummy"}):
            with self.assertRaises(SystemExit):
                zodiac_cardnews.publish_carousel(["https://example.org/a.png"], "text", "2026-11-05")
        post.assert_called_once()


class InstagramGuardTests(unittest.TestCase):
    @patch.object(zodiac_instagram, "_skip_if_done", return_value=False)
    @patch.object(zodiac_instagram, "reel_media_url", return_value="https://example.org/variant.mp4")
    @patch.object(zodiac_instagram, "reel_caption", return_value="caption")
    @patch.object(zodiac_instagram, "_write_marker")
    @patch.object(zodiac_instagram, "add_comment")
    @patch.object(zodiac_instagram, "publish_reel")
    def test_404_variant_falls_back_to_shared_video(self, publish, comment, marker, caption, variant, skip):
        publish.side_effect = [FileNotFoundError("HTTP 404"), "postid"]
        zodiac_instagram.do_reel("2026-11-05")
        self.assertEqual(publish.call_count, 2)
        self.assertIn("_tts.mp4", publish.call_args.args[0])
        marker.assert_called_once()
        comment.assert_called_once()

    @patch.object(zodiac_instagram.time, "sleep")
    @patch.object(zodiac_instagram, "_env", return_value=("uid", "token"))
    @patch.object(zodiac_instagram, "_remote_media_ready", return_value=(True, "ready"))
    @patch.object(zodiac_instagram, "_post")
    @patch.object(zodiac_instagram.requests, "get")
    def test_media_processing_error_retries_container_not_publish(self, get, post, ready, env, sleep):
        post.side_effect = [{"id": "container1"}, {"id": "container2"}, {"id": "posted"}]
        get.side_effect = [
            MagicMock(json=lambda: {"status_code": "ERROR"}),
            MagicMock(json=lambda: {"status_code": "FINISHED"}),
        ]
        pid = zodiac_instagram.publish_reel("https://example.org/video.mp4", "caption")
        self.assertEqual(pid, "posted")
        self.assertEqual(post.call_count, 3)
        publish_calls = [c for c in post.call_args_list if "media_publish" in c.args[0]]
        self.assertEqual(len(publish_calls), 1)

    @patch.object(zodiac_instagram.time, "sleep")
    @patch.object(zodiac_instagram, "_env", return_value=("uid", "token"))
    @patch.object(zodiac_instagram, "_remote_media_ready", return_value=(True, "ready"))
    @patch.object(zodiac_instagram, "_post", side_effect=[{"id": "container1"}, {"id": "container2"}])
    @patch.object(zodiac_instagram.requests, "get")
    def test_two_processing_errors_never_publish(self, get, post, ready, env, sleep):
        get.return_value = MagicMock(json=lambda: {"status_code": "ERROR"})
        with self.assertRaises(RuntimeError):
            zodiac_instagram.publish_reel("https://example.org/video.mp4", "caption")
        self.assertEqual(post.call_count, 2)
        self.assertFalse(any("media_publish" in c.args[0] for c in post.call_args_list))

    @patch.object(zodiac_instagram, "_skip_if_done", return_value=False)
    @patch.object(zodiac_instagram, "publish_reel", side_effect=RuntimeError("Meta video status ERROR"))
    def test_video_processing_error_stops_without_blind_republish(self, publish, skip):
        with self.assertRaises(RuntimeError):
            zodiac_instagram.do_reel("2026-11-05")
        publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
