"""Offline QA of short cover/CTA only; preserve all 12 daily Saju readings."""
import os
import pytest
import zodiac_reels as r
import zodiac_cardnews_tpl as tpl

DAY = "2026-12-07"


def _setup(monkeypatch, *, day=DAY):
    monkeypatch.setenv("ZODIAC_M2_READABLE_PACE_PILOT","1")
    monkeypatch.setenv("ZODIAC_DOG_M2_CLARITY_PILOT","1")
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    monkeypatch.setenv("SUPERTONIC_VOICE","M2")
    monkeypatch.setattr(tpl,"_flux_active",lambda d:d==day)


def _prepared(date):
    old=r.narration_lines(date)
    new=old[:]
    new[4]=new[4].replace("개띠, ","이어서 개띠 운세입니다. ",1)
    return new


def test_default_disabled_does_not_alter_source_or_legacy(monkeypatch):
    monkeypatch.delenv("ZODIAC_M2_READABLE_PACE_PILOT",raising=False)
    item=_prepared(DAY)
    assert r._optional_m2_readable_pace_pilot(DAY,"card_",item) is item


@pytest.mark.parametrize("day",["2026-12-07","2026-12-08","2026-12-09"])
def test_only_cover_and_close_are_reduced_and_all_12_kept(monkeypatch,day):
    _setup(monkeypatch,day=day)
    original=_prepared(day)
    before=original[:]
    updated=r._optional_m2_readable_pace_pilot(day,"card_",original)
    assert original==before
    assert len(updated)==len(original)==6
    assert updated[1:5]==original[1:5]
    assert len(updated[0])<len(original[0])
    assert len(updated[5])<len(original[5])
    assert r.date_full(day) in updated[0]
    assert "열두 띠 운세" in updated[0]
    assert "사주포춘" in updated[5]
    top=original[5].split("오늘 운이 좋은 띠는 ",1)[1].split(". ",1)[0]
    assert top in updated[5]


@pytest.mark.parametrize("key,val",[
 ("SUPERTONIC_VOICE","F2"),
 ("SUPERTONIC_VOICE",""),
 ("ZODIAC_REQUIRE_HANBOK_AVATAR","0"),
 ("ZODIAC_DOG_M2_CLARITY_PILOT","0"),
])
def test_rejects_non_strict_or_non_male(monkeypatch,key,val):
    _setup(monkeypatch)
    monkeypatch.setenv(key,val)
    with pytest.raises(RuntimeError,match="READABLE_PACE_REQUIRES_STRICT_FLUX_M2_DOG_QA"):
        r._optional_m2_readable_pace_pilot(DAY,"card_",_prepared(DAY))


def test_rejects_legacy_date(monkeypatch):
    _setup(monkeypatch)
    monkeypatch.setattr(tpl,"_flux_active",lambda d:False)
    with pytest.raises(RuntimeError,match="READABLE_PACE_REQUIRES_VERIFIED_FLUX_DATE"):
        r._optional_m2_readable_pace_pilot(DAY,"card_",_prepared(DAY))


def test_rejects_signal_shortform(monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(RuntimeError,match="READABLE_PACE_REQUIRES_STRICT_FLUX_M2_DOG_QA"):
        r._optional_m2_readable_pace_pilot(DAY,"signal_",_prepared(DAY))


def test_rejects_missing_sign_scene(monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(RuntimeError,match="READABLE_PACE_REQUIRES_SIX_ZODIAC_SCENES"):
        r._optional_m2_readable_pace_pilot(DAY,"card_",_prepared(DAY)[:-1])


@pytest.mark.parametrize("scene,script",[(0,"개띠 먼저 입니다"),(5,"사주 풀이는 유료")])
def test_rejects_unexpected_cover_or_cta(monkeypatch,scene,script):
    _setup(monkeypatch)
    narration=_prepared(DAY)
    narration[scene]=script
    with pytest.raises(RuntimeError,match="READABLE_PACE_UNEXPECTED_COVER_OR_CTA"):
        r._optional_m2_readable_pace_pilot(DAY,"card_",narration)


@pytest.mark.parametrize("rate,total,should_pass",[
 (20,84.50,True),(24,85.0,True),(25,80,False),(31,80.0,False),(20,85.01,False),
])
def test_readability_length_gate(monkeypatch,rate,total,should_pass):
    _setup(monkeypatch)
    if should_pass:
        assert r._assert_readable_pace_length(rate,total) is None
    else:
        with pytest.raises(RuntimeError,match="READABLE_PACE_QA_HOLD_TOO_FAST_OR_LONG"):
            r._assert_readable_pace_length(rate,total)


def test_no_extra_hold_when_off(monkeypatch):
    monkeypatch.delenv("ZODIAC_M2_READABLE_PACE_PILOT",raising=False)
    assert r._assert_readable_pace_length(35,100.0) is None
