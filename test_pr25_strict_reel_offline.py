"""Independent negative/positive tests for candidate strict Hanbok reel path. No network, uploads or paid calls."""
import datetime as dt
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

import zodiac_reels as reels
import zodiac_shorts as shorts
from scripts.zodiac_character_prompts import NAMES


def fake_avatar(monkeypatch, *, enabled=True, apply=None):
    module=SimpleNamespace(enabled=lambda: enabled,apply=apply or (lambda *args,**kw: True))
    monkeypatch.setitem(sys.modules,"avatar_pip",module)
    return module


def test_existing_flux_default_skips_human_avatar(tmp_path,monkeypatch):
    monkeypatch.delenv("ZODIAC_REQUIRE_HANBOK_AVATAR",raising=False)
    calls=[]
    fake_avatar(monkeypatch,enabled=True,apply=lambda *a,**kw:calls.append(1))
    result=reels._apply_reel_avatar(tmp_path/"nonexistent.mp4","2026-12-07","card_",True)
    assert result=="SKIPPED_LEGACY_FLUX" and not calls


def test_required_flux_blocks_disabled_avatar(tmp_path,monkeypatch):
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    fake_avatar(monkeypatch,enabled=False)
    with pytest.raises(RuntimeError,match="HANBOK_AVATAR_REQUIRED_BUT_DISABLED"):
        reels._apply_reel_avatar(tmp_path/"z.mp4","2026-12-07","card_",True)


def test_required_flux_blocks_undeclared_gender(tmp_path,monkeypatch):
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    monkeypatch.delenv("SUPERTONIC_VOICE",raising=False)
    fake_avatar(monkeypatch,enabled=True)
    with pytest.raises(RuntimeError,match="HANBOK_AVATAR_TTS_VOICE_NOT_DECLARED"):
        reels._apply_reel_avatar(tmp_path/"z.mp4","2026-12-07","card_",True)


def test_required_flux_blocks_failed_apply(tmp_path,monkeypatch):
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    monkeypatch.setenv("SUPERTONIC_VOICE","M2")
    fake_avatar(monkeypatch,enabled=True,apply=lambda *a,**kw:False)
    p=tmp_path/"z.mp4";p.write_bytes(b"unchanged")
    with pytest.raises(RuntimeError,match="HANBOK_AVATAR_COMPOSITING_FAILED"):
        reels._apply_reel_avatar(p,"2026-12-07","card_",True)


def test_required_flux_blocks_noop(tmp_path,monkeypatch):
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    monkeypatch.setenv("SUPERTONIC_VOICE","F2")
    fake_avatar(monkeypatch,enabled=True,apply=lambda *a,**kw:True)
    p=tmp_path/"z.mp4";p.write_bytes(b"unchanged")
    with pytest.raises(RuntimeError,match="HANBOK_AVATAR_COMPOSITING_NOOP"):
        reels._apply_reel_avatar(p,"2026-12-07","card_",True)


@pytest.mark.parametrize("gender",["M2","F2"])
def test_required_flux_passes_only_actual_changed_file_with_expected_voice(tmp_path,monkeypatch,gender):
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    monkeypatch.setenv("SUPERTONIC_VOICE",gender)
    def apply(p,voice=None,left_rail=False):
        assert voice==gender and left_rail is True
        Path(p).write_bytes(b"video_with_avatar_for_"+gender.encode())
        return True
    fake_avatar(monkeypatch,enabled=True,apply=apply)
    p=tmp_path/"z.mp4";p.write_bytes(b"before")
    assert reels._apply_reel_avatar(p,"2026-12-07","card_",True)=="APPLIED_QA_PENDING_VISUAL"
    assert p.read_bytes()!=b"before"


def test_strict_tts_fail_cannot_fallback_to_gender_mismatched_edge(tmp_path,monkeypatch):
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    monkeypatch.setitem(sys.modules,"tts_supertonic",SimpleNamespace(synth=lambda *a,**kw:False))
    monkeypatch.setattr(reels,"edge_tts",SimpleNamespace(Communicate=lambda *a,**kw:(_ for _ in ()).throw(AssertionError("EDGE_NOT_ALLOWED"))))
    with pytest.raises(RuntimeError,match="HANBOK_VOICE_GENDER_UNVERIFIED_LOCAL_TTS_FAILED"):
        reels._tts("테스트",tmp_path/"n.mp3")


def test_full_reel_narration_has_all_12_zodiac_in_order():
    from zodiac_reels import ORDER, narration_lines
    assert tuple(ORDER)==tuple(NAMES)
    narrs=narration_lines("2026-12-07")
    assert len(narrs)==6
    for scene_idx in range(4):
        text=narrs[scene_idx+1]
        animals=ORDER[scene_idx*3:scene_idx*3+3]
        positions=[text.find({"rat":"쥐띠","ox":"소띠","tiger":"호랑이띠","rabbit":"토끼띠","dragon":"용띠","snake":"뱀띠","horse":"말띠","goat":"양띠","monkey":"원숭이띠","rooster":"닭띠","dog":"개띠","pig":"돼지띠"}[n]) for n in animals]
        assert -1 not in positions and positions==sorted(positions)


def test_real_workflow_does_not_yet_require_hanbok_gate():
    # This is a deliberate failing-release precondition, NOT a unit test
    # claiming the real scheduler is already safe.
    workflow=(Path(__file__).parent/".github/workflows/zodiac-cards.yml").read_text()
    assert "ZODIAC_AVATAR: \"1\"" in workflow
    assert "ZODIAC_REQUIRE_HANBOK_AVATAR:" not in workflow
    assert "ZODIAC_ALLOW_HUMAN_PIP:" not in workflow
