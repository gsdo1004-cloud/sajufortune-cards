"""Isolated tests for opt-in fail-closed Hanbok avatar QA; no external posting."""
import datetime as dt
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import zodiac_shorts as shorts


def test_required_hanbok_cannot_silently_skip_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    monkeypatch.delenv("ZODIAC_ALLOW_HUMAN_PIP",raising=False)
    with pytest.raises(RuntimeError, match="HANBOK_AVATAR_REQUIRED_BUT_DISABLED"):
        shorts._apply_pngtuber_pip(tmp_path/"video.mp4",dt.date(2026,11,28),
                                  {"gender":"male"})


def test_missing_avatar_frames_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    monkeypatch.setenv("ZODIAC_ALLOW_HUMAN_PIP","1")
    monkeypatch.setattr(shorts,"PNGTUBER_AVATAR_ROOT",tmp_path/"no_assets")
    monkeypatch.setattr(shorts,"PNGTUBER_DIR",tmp_path)
    monkeypatch.setitem(sys.modules,"pngtuber_shorts_pip",SimpleNamespace(compose=lambda *a,**k:None))
    with pytest.raises(RuntimeError, match="HANBOK_AVATAR_FRAMES_MISSING"):
        shorts._apply_pngtuber_pip(tmp_path/"video.mp4",dt.date(2026,11,28),
                                  {"gender":"female"})


def _frames_for(tmp_path,gender):
    persona=shorts.PNGTUBER_PERSONA[gender]
    folder=tmp_path/persona
    folder.mkdir()
    for frame in shorts.PNGTUBER_MOUTH_FILES:
        (folder/frame).write_bytes(b"synthetic-frame-not-real-art")
    return folder


def test_pip_noop_is_not_counted_as_pass(tmp_path,monkeypatch):
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    monkeypatch.setenv("ZODIAC_ALLOW_HUMAN_PIP","1")
    monkeypatch.setattr(shorts,"PNGTUBER_AVATAR_ROOT",tmp_path)
    monkeypatch.setattr(shorts,"PNGTUBER_DIR",tmp_path)
    _frames_for(tmp_path,"male")
    clip=tmp_path/"test.mp4";clip.write_bytes(b"fake-video")
    module=SimpleNamespace(compose=lambda path,frames:{"위치":"rail","길이":5.0})
    monkeypatch.setitem(sys.modules,"pngtuber_shorts_pip",module)
    with pytest.raises(RuntimeError, match="HANBOK_AVATAR_NOT_COMPOSITED"):
        shorts._apply_pngtuber_pip(clip,dt.date(2026,11,28),{"gender":"male"})


def test_required_hanbok_tracks_actual_gender_and_changed_output(tmp_path,monkeypatch):
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    monkeypatch.setenv("ZODIAC_ALLOW_HUMAN_PIP","1")
    monkeypatch.setattr(shorts,"PNGTUBER_AVATAR_ROOT",tmp_path)
    monkeypatch.setattr(shorts,"PNGTUBER_DIR",tmp_path)
    _frames_for(tmp_path,"female")
    clip=tmp_path/"test.mp4";clip.write_bytes(b"fake-video")
    def fake_compose(path,frames):
        assert "frames_female_hanbok" in frames[0]
        Path(path).write_bytes(b"changed-video")
        return {"위치":"rail","길이":5.0}
    monkeypatch.setitem(sys.modules,"pngtuber_shorts_pip",SimpleNamespace(compose=fake_compose))
    result=shorts._apply_pngtuber_pip(clip,dt.date(2026,11,28),{"gender":"female"})
    assert result == {"status":"APPLIED","persona":"frames_female_hanbok","gender":"female"}
