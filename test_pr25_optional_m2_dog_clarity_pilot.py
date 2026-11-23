"""Opt-in only narration clarity A/B for strict FLUX M2 dog sign.
Never authorizes release or calls social/upload/network providers."""
from __future__ import annotations
import os
import pytest
import zodiac_reels as reels
import zodiac_cardnews_tpl as tpl

DAY="2026-12-07"


def _flags(monkeypatch):
    monkeypatch.setenv("ZODIAC_DOG_M2_CLARITY_PILOT", "1")
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR", "1")
    monkeypatch.setenv("SUPERTONIC_VOICE", "M2")
    monkeypatch.setattr(tpl, "_flux_active", lambda date: date == DAY)


def test_default_off_is_exact_noop(monkeypatch):
    monkeypatch.delenv("ZODIAC_DOG_M2_CLARITY_PILOT", raising=False)
    lines=reels.narration_lines(DAY)
    assert reels._optional_m2_dog_clarity_pilot(DAY,"card_",lines) is lines
    assert lines[4].count("개띠, ")==1


def test_strict_opt_in_replaces_only_one_announcement_without_reading_changes(monkeypatch):
    _flags(monkeypatch)
    before=reels.narration_lines(DAY)
    unchanged=before[:]
    after=reels._optional_m2_dog_clarity_pilot(DAY,"card_",before)
    assert before==unchanged
    assert after is not before and len(after)==6
    assert all(after[i]==before[i] for i in (0,1,2,3,5))
    assert after[4]==before[4].replace("개띠, ","이어서 개띠 운세입니다. ",1)
    assert "개띠 운세입니다" in after[4]
    assert "닭띠" in after[4] and "돼지띠" in after[4]
    assert after[4].count("개띠")==1


@pytest.mark.parametrize("env_name,env_value", [
    ("SUPERTONIC_VOICE","F2"),
    ("SUPERTONIC_VOICE",""),
    ("ZODIAC_REQUIRE_HANBOK_AVATAR","0"),
])
def test_opt_in_rejects_nonmatching_gender_or_non_strict(monkeypatch,env_name,env_value):
    _flags(monkeypatch)
    monkeypatch.setenv(env_name,env_value)
    with pytest.raises(RuntimeError,match="DOG_CLARITY_PILOT_REQUIRES_STRICT_M2_HANBOK"):
        reels._optional_m2_dog_clarity_pilot(DAY,"card_",reels.narration_lines(DAY))


def test_opt_in_rejects_legacy_or_non_flux(monkeypatch):
    _flags(monkeypatch)
    monkeypatch.setattr(tpl,"_flux_active",lambda date:False)
    with pytest.raises(RuntimeError,match="DOG_CLARITY_PILOT_REQUIRES_VERIFIED_FLUX_DATE"):
        reels._optional_m2_dog_clarity_pilot(DAY,"card_",reels.narration_lines(DAY))


def test_opt_in_rejects_signal_cards(monkeypatch):
    _flags(monkeypatch)
    with pytest.raises(RuntimeError,match="DOG_CLARITY_PILOT_REQUIRES_STRICT_M2_HANBOK"):
        reels._optional_m2_dog_clarity_pilot(DAY,"signal_",reels.narration_lines(DAY))


def test_opt_in_rejects_silent_missing_dog_sign(monkeypatch):
    _flags(monkeypatch)
    input_lines=reels.narration_lines(DAY)
    input_lines[4]=input_lines[4].replace("개띠, ","")
    with pytest.raises(RuntimeError,match="DOG_CLARITY_PILOT_SIGN_COUNT_MISMATCH"):
        reels._optional_m2_dog_clarity_pilot(DAY,"card_",input_lines)


def test_opt_in_rejects_duplicate_dog_label(monkeypatch):
    _flags(monkeypatch)
    lines=reels.narration_lines(DAY)
    lines[4]="개띠, "+lines[4]
    with pytest.raises(RuntimeError,match="DOG_CLARITY_PILOT_SIGN_COUNT_MISMATCH"):
        reels._optional_m2_dog_clarity_pilot(DAY,"card_",lines)


def test_opt_in_rejects_short_narration_list(monkeypatch):
    _flags(monkeypatch)
    with pytest.raises(RuntimeError,match="DOG_CLARITY_PILOT_REQUIRES_SIX_SCENES"):
        reels._optional_m2_dog_clarity_pilot(DAY,"card_",reels.narration_lines(DAY)[:3])
