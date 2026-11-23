"""PR25 repair defense-in-depth tests with no external network or publication."""
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import zodiac_publish_guard as guard
from scripts import zodiac_safe_public_stage as stage
import zodiac_reels as reels


def _fake(tmp, day, ext=".png", variants=()):
    card_dir=tmp/"cards"/day
    card_dir.mkdir(parents=True,exist_ok=True)
    for i in range(1,7):
        (card_dir/f"card_{i:02d}{ext}").write_bytes(b"not-a-real-card")
    reel=tmp/"reels"
    reel.mkdir(exist_ok=True)
    (reel/f"{day}_tts.mp4").write_bytes(b"not-a-real-mp4")
    for v in variants:
        (reel/f"{day}_tts_ig_{v}.mp4").write_bytes(b"not-a-real-mp4")


def test_legitimate_legacy_png_is_scoped_without_other_files(tmp_path):
    day="2026-10-21"
    _fake(tmp_path,day)
    (tmp_path/"cards"/day/"unreviewed.json").write_text("ignore")
    (tmp_path/"reels"/"2099-01-01_tts.mp4").write_bytes(b"not-target")
    files=stage.allowed_paths(day,tmp_path)
    assert len(files)==7
    assert f"reels/{day}_tts.mp4" in files
    assert not any("unreviewed" in x or "2099" in x for x in files)


def test_future_JPEG_without_signed_source_fails_before_any_git_stage(tmp_path, monkeypatch):
    day="2026-12-07"
    _fake(tmp_path,day,ext=".jpg")
    with pytest.raises(guard.ReleaseHold,match="RELEASE_STYLED_ASSETS_WITHOUT_MANIFEST"):
        stage.allowed_paths(day,tmp_path)


def test_styled_only_individually_approved_variants_enter_raw_hosting(tmp_path,monkeypatch):
    day="2026-12-07"
    _fake(tmp_path,day,ext=".jpg",variants=("A","B"))
    monkeypatch.setattr(stage,"styled_manifest",lambda *a:{"style_id":"STYLE_01"})
    checked=[]
    def check(day,*,root,mode,video=None):
        checked.append((mode,Path(video).name if video else None))
        if video and Path(video).name.endswith("_ig_B.mp4"):
            raise guard.ReleaseHold("RELEASE_VIDEO_SHA_UNAPPROVED")
        return {"status":"VERIFIED_SIGNED_RELEASE"}
    monkeypatch.setattr(stage,"check",check)
    files=stage.allowed_paths(day,tmp_path)
    assert len(files)==8
    assert f"reels/{day}_tts_ig_A.mp4" in files
    assert f"reels/{day}_tts_ig_B.mp4" not in files
    assert checked==[("cards",None),("video",f"{day}_tts.mp4"),
                     ("video",f"{day}_tts_ig_A.mp4"),("video",f"{day}_tts_ig_B.mp4")]


def test_raw_url_rejects_mutable_branch_for_signed_media(monkeypatch):
    url="https://raw.githubusercontent.com/gsdo1004-cloud/sajufortune-cards/main/reels/2026-12-07_tts.mp4"
    monkeypatch.delenv("ZODIAC_RAW_COMMIT_SHA",raising=False)
    with pytest.raises(guard.ReleaseHold,match="RELEASE_IMMUTABLE_RAW_COMMIT_UNAVAILABLE"):
        guard.immutable_raw_url(url)
    monkeypatch.setenv("ZODIAC_RAW_COMMIT_SHA","a"*40)
    frozen=guard.immutable_raw_url(url)
    assert "/"+("a"*40)+"/" in frozen
    with pytest.raises(guard.ReleaseHold,match="RELEASE_REMOTE_URL_NOT_APPROVED"):
        guard.verify_remote_sha(url,"a"*64,require_immutable=True)


def test_twelve_spoken_label_validator_rejects_missing_and_swapped():
    day="2026-12-07"
    lines=reels.narration_lines(day)
    reels._validate_twelve_zodiac_narration(day,lines)
    missing=list(lines)
    missing[1]=missing[1].replace("소띠, ","",1)
    with pytest.raises(RuntimeError,match="TTS_TWELVE_ZODIAC_NAME_MISSING_OR_DUPLICATED"):
        reels._validate_twelve_zodiac_narration(day,missing)
    swapped=list(lines)
    line=swapped[1]
    swapped[1]=line.replace("쥐띠, ","PLACEHOLDER").replace("소띠, ","쥐띠, ").replace("PLACEHOLDER","소띠, ")
    with pytest.raises(RuntimeError,match="TTS_TWELVE_ZODIAC_ORDER_MISMATCH"):
        reels._validate_twelve_zodiac_narration(day,swapped)


def test_dog_pilot_ignores_incidental_lucky_three_repeat(monkeypatch):
    day="2026-12-07"
    monkeypatch.setenv("ZODIAC_DOG_M2_CLARITY_PILOT","1")
    monkeypatch.setenv("SUPERTONIC_VOICE","M2")
    monkeypatch.setenv("ZODIAC_REQUIRE_HANBOK_AVATAR","1")
    import zodiac_cardnews_tpl
    monkeypatch.setattr(zodiac_cardnews_tpl,"_flux_active",lambda *args:True)
    lines=reels.narration_lines(day)
    lines[5]+=" 개띠, 추천 대상입니다."
    result=reels._optional_m2_dog_clarity_pilot(day,"card_",lines)
    assert result[4].count("개띠 운세입니다")==1
    assert result[5]==lines[5]


def test_main_workflow_stages_only_verified_and_immutable_hash():
    root=Path(__file__).resolve().parent
    workflow=(root/".github/workflows/zodiac-cards.yml").read_text(encoding="utf-8")
    assert 'git add cards/ reels/' not in workflow
    assert 'python scripts/zodiac_safe_public_stage.py "$TARGET" --stage' in workflow
    assert 'ZODIAC_RAW_COMMIT_SHA=' in workflow
    assert workflow.index("zodiac_safe_public_stage.py") < workflow.index("raw URL 전파 대기")
    inventory=(root/".github/workflows/zodiac-card-assets.yml").read_text(encoding="utf-8")
    assert 'zodiac_publish_guard.py cards "$DAY"' in inventory
    assert 'git add -A -- "cards/$DAY"' not in inventory


def test_supertonic_failure_does_not_reuse_old_mp3(tmp_path, monkeypatch):
    import tts_supertonic as st
    class Engine:
        def get_voice_style(self,voice_name):return object()
        def synthesize(self,**kwargs):return (b"wav",None)
        def save_audio(self,wav,path):Path(path).write_bytes(b"wav"*500)
    monkeypatch.setattr(st,"_engine",lambda:Engine())
    monkeypatch.setattr(st,"_FAILED",False)
    def fails(*args,**kwargs):
        raise subprocess.CalledProcessError(1,"ffmpeg")
    monkeypatch.setattr(st.subprocess,"run",fails)
    old=tmp_path/"a.mp3";old.write_bytes(b"STALE_MP3"*1200)
    assert not st.synth("changed narration",old)
    assert not old.exists()
    assert not list(tmp_path.glob("*.staging.mp3"))
    assert not list(tmp_path.glob("*.st.wav"))


def test_youtube_success_receipt_requires_matching_current_title_and_fresh_log(tmp_path, monkeypatch):
    import time
    import zodiac_daily_pipeline as pipeline
    monkeypatch.setattr(pipeline,"BASE",tmp_path)
    monkeypatch.setattr(pipeline,"UPLOADER_DIR",tmp_path / "uploader")
    day="2026-12-07"
    (tmp_path/"cards"/day).mkdir(parents=True)
    logs=tmp_path/"uploader"/"logs"
    logs.mkdir(parents=True)
    before=time.time()-2
    logfile=logs/"upload_unmyeong_test.json"
    logfile.write_text(json.dumps([{"status":"success","title":"different title",
                                    "video_id":"WRONG"}]))
    assert pipeline._record_upload(day, expected_title="exact target", started_at=before)== ""
    assert not (tmp_path/"cards"/day/"uploaded.json").exists()
    logfile.write_text(json.dumps([{"status":"success","title":"exact target",
                                    "video_id":"FAKE_ID_DO_NOT_USE"}]))
    assert pipeline._record_upload(day, expected_title="exact target", started_at=before)=="FAKE_ID_DO_NOT_USE"
    receipt=json.loads((tmp_path/"cards"/day/"uploaded.json").read_text())
    assert receipt["title"]=="exact target" and receipt["date"]==day


def test_cached_old_log_does_not_create_new_youtube_upload_receipt(tmp_path, monkeypatch):
    import time,os
    import zodiac_daily_pipeline as pipeline
    monkeypatch.setattr(pipeline,"BASE",tmp_path)
    monkeypatch.setattr(pipeline,"UPLOADER_DIR",tmp_path/"uploader")
    day="2026-12-07"
    (tmp_path/"cards"/day).mkdir(parents=True)
    logs=tmp_path/"uploader"/"logs";logs.mkdir(parents=True)
    logfile=logs/"upload_unmyeong_old.json"
    logfile.write_text(json.dumps([{"status":"success","title":"same","video_id":"STALE"}]))
    os.utime(logfile,(time.time()-500,time.time()-500))
    assert pipeline._record_upload(day,expected_title="same",started_at=time.time())==""
    assert not (tmp_path/"cards"/day/"uploaded.json").exists()
