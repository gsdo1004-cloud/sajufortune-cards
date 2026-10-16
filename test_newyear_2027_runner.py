import hashlib
import json
import re
from pathlib import Path

import pytest

import newyear_2027_runner as ny


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _post(tmp_path: Path, *, index=1, slug="wealth", publish_date="2026-10-16") -> tuple[Path, str]:
    post = tmp_path / f"{index:02d}_{slug}"
    post.mkdir(parents=True)
    article = """# 2027년 재물운 총정리

2027년은 정미(丁未)년입니다. 재물운은 재성 하나만 보는 것이 아니라 원국과 대운의 흐름을 함께 봐야 합니다.

## 30초 핵심 요약

- 2027년은 돈이 들어오느냐보다 현금흐름과 계약 구조를 정리하는 것이 중요합니다.
- 재성이 보여도 일간의 힘과 식상·관성 연결을 함께 확인해야 합니다.
- 고정비·부채·비상자금·계약 만기와 세금을 먼저 점검하세요.

## 자세히 보기

같은 정미년이라도 원래 사주와 현재 대운에 따라 체감이 달라집니다.
"""
    (post / "article.md").write_text(article, encoding="utf-8")
    (post / "meta.json").write_text(json.dumps({
        "index": index,
        "slug": slug,
        "publish_date": publish_date,
        "status": "READY_TO_PUBLISH",
        "naver_title": "2027년 재물운 총정리｜돈이 들어오는 흐름보다 먼저 봐야 할 것",
        "source_url": "https://sajufortune.kr/2027/wealth",
        "group": "theme",
    }, ensure_ascii=False), encoding="utf-8")
    (post / "naver_publish.json").write_text(json.dumps({
        "success": True,
        "status": "PUBLISHED",
        "rss_seen": True,
        "url": "https://blog.naver.com/gsd1004/123",
        "category": "2027 신년운세",
    }, ensure_ascii=False), encoding="utf-8")
    return post, article


def test_validate_naver_receipt_accepts_only_confirmed_publish(tmp_path):
    post, _ = _post(tmp_path)
    ok = ny.validate_naver_receipt(post / "naver_publish.json")
    assert ok["ok"] is True
    assert ok["url"].startswith("https://blog.naver.com/")

    data = json.loads((post / "naver_publish.json").read_text(encoding="utf-8"))
    for field, bad in [("success", False), ("status", "PUBLISHING"), ("rss_seen", False), ("url", ""), ("category", "기타")]:
        broken = dict(data)
        broken[field] = bad
        path = post / f"broken_{field}.json"
        path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        result = ny.validate_naver_receipt(path)
        assert result["ok"] is False, (field, result)


def test_validate_naver_receipt_rejects_missing_and_corrupt(tmp_path):
    assert ny.validate_naver_receipt(tmp_path / "missing.json")["ok"] is False
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    assert ny.validate_naver_receipt(bad)["ok"] is False


def test_select_manifest_item_rejects_duplicate_date():
    manifest = {"items": [
        {"content_id": "a", "publish_date": "2026-10-16"},
        {"content_id": "b", "publish_date": "2026-10-16"},
    ]}
    with pytest.raises(ValueError, match="duplicate"):
        ny.select_manifest_item(manifest, "2026-10-16")


def test_select_manifest_item_returns_none_when_no_due():
    manifest = {"items": [{"content_id": "a", "publish_date": "2026-10-17"}]}
    assert ny.select_manifest_item(manifest, "2026-10-16") is None


def test_source_gate_requires_hash_receipt_and_existing_readiness(tmp_path):
    post, article = _post(tmp_path)
    item = {
        "content_id": "ny2027-001-wealth",
        "source_dir": post.name,
        "publish_date": "2026-10-16",
        "source_sha256": _sha(article),
    }
    good = ny.source_gate(item, tmp_path, readiness_fn=lambda p: {"ready": True, "reasons": []})
    assert good["ok"] is True

    (post / "article.md").write_text(article + "\nchanged", encoding="utf-8")
    stale = ny.source_gate(item, tmp_path, readiness_fn=lambda p: {"ready": True, "reasons": []})
    assert stale["ok"] is False
    assert stale["reason"] == "source_hash_mismatch"

    (post / "article.md").write_text(article, encoding="utf-8")
    not_ready = ny.source_gate(item, tmp_path, readiness_fn=lambda p: {"ready": False, "reasons": ["editorial_review_stale"]})
    assert not_ready["ok"] is False
    assert "editorial_review_stale" in not_ready["reason"]


def test_owned_lock_does_not_delete_foreign_lock(tmp_path):
    path = tmp_path / "fanout.lock"
    path.write_text('{"owner":"other"}', encoding="utf-8")
    with pytest.raises(FileExistsError):
        with ny.OwnedFileLock(path):
            pass
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["owner"] == "other"


def test_owned_lock_removes_only_its_own_file(tmp_path):
    path = tmp_path / "fanout.lock"
    with ny.OwnedFileLock(path):
        assert path.exists()
        current = json.loads(path.read_text(encoding="utf-8"))
        assert current["owner"]
    assert not path.exists()


def test_two_phase_receipt_blocks_unresolved_publish_and_preserves_publish_key(tmp_path):
    p = tmp_path / "threads.json"
    item = {"content_id": "ny2027-001-wealth", "source_sha256": "aaa", "output_sha256": "bbb"}
    intent = ny.prepare_intent(p, item=item, platform="threads", account="gsdo10042026")
    assert intent["status"] == "PUBLISHING"
    assert intent["publish_key"] == "ny2027-001-wealth:threads:gsdo10042026"

    with pytest.raises(ny.PublicationBlocked, match="PUBLISHING"):
        ny.prepare_intent(p, item={**item, "source_sha256": "changed"}, platform="threads", account="gsdo10042026")

    final = ny.finalize_receipt(p, remote_id="th_123")
    assert final["status"] == "PUBLISHED"
    assert final["remote_id"] == "th_123"
    assert final["publish_key"] == intent["publish_key"]

    with pytest.raises(ny.PublicationBlocked, match="PUBLISHED"):
        ny.prepare_intent(p, item={**item, "source_sha256": "another"}, platform="threads", account="gsdo10042026")


def test_build_entry_creates_native_threads_and_grounded_shorts(tmp_path):
    post, article = _post(tmp_path)
    entry = ny.build_entry(post)
    assert entry["content_id"] == "ny2027-001-wealth"
    assert entry["source_sha256"] == _sha(article)
    assert entry["publish_date"] == "2026-10-16"
    assert len(entry["threads_text"]) <= 500
    assert "저장" in entry["threads_text"] or "댓글" in entry["threads_text"]
    first_two = entry["threads_text"].splitlines()[:2]
    assert len(first_two) == 2 and all(first_two)
    assert "2027" in entry["shorts_script"]
    assert any(term in entry["shorts_script"] for term in ("정미년", "명리", "대운", "재성", "일간"))
    assert 130 <= len(entry["shorts_script"]) <= 300


def test_build_entry_rotates_six_formats(tmp_path):
    formats = []
    for idx in range(1, 7):
        post, _ = _post(tmp_path, index=idx, slug=f"topic{idx}", publish_date=f"2026-10-{15+idx:02d}")
        formats.append(ny.build_entry(post)["format"])
    assert formats == list(ny.CONTENT_FORMATS)
    assert len(set(formats)) == 6


class _FakeThreadsApi:
    def __init__(self, *, fail=False):
        self.calls = []
        self.uid_tokens = []
        self.fail = fail

    def _threads_uid(self, token):
        self.uid_tokens.append(token)
        return "threads_uid_1"

    def _post(self, url, data):
        self.calls.append((url, dict(data)))
        if self.fail:
            raise RuntimeError("threads down")
        if url.endswith("/threads_publish"):
            return {"id": "threads_post_123"}
        return {"id": "threads_container_123"}


class _FakeYoutubeUploader:
    EXPECT_CHANNEL_TITLE = "운명과학TV"

    def __init__(self, video_id="youtube_123"):
        self.video_id = video_id
        self.calls = []

    def upload(self, **kwargs):
        self.calls.append(kwargs)
        return self.video_id


def _intent_item():
    return {
        "content_id": "ny2027-001-wealth",
        "source_sha256": "source-sha",
        "output_sha256": "video-sha",
        "threads_text": "첫 줄\n둘째 줄\n저장하세요.",
        "youtube_title": "2027 재물운",
        "youtube_description": "설명",
        "tags": ["2027운세"],
    }


def test_publish_threads_requires_committed_intent_before_remote(tmp_path, monkeypatch):
    api = _FakeThreadsApi()
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "token")
    receipt = tmp_path / "threads.json"
    with pytest.raises(ny.PublicationBlocked, match="intent"):
        ny.publish_threads_text(_intent_item(), receipt_path=receipt, account="gsdo10042026", api_module=api, sleep_fn=lambda _: None)
    assert api.calls == []
    assert api.uid_tokens == []


def test_publish_threads_delegates_account_guard_and_finalizes(tmp_path, monkeypatch):
    api = _FakeThreadsApi()
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "token")
    receipt = tmp_path / "threads.json"
    item = _intent_item()
    ny.prepare_intent(receipt, item=item, platform="threads", account="gsdo10042026")
    remote_id = ny.publish_threads_text(item, receipt_path=receipt, account="gsdo10042026", api_module=api, sleep_fn=lambda _: None)
    assert remote_id == "threads_post_123"
    assert api.uid_tokens == ["token"]
    assert api.calls[0][1]["media_type"] == "TEXT"
    assert api.calls[0][1]["text"] == item["threads_text"]
    final = json.loads(receipt.read_text(encoding="utf-8"))
    assert final["status"] == "PUBLISHED"
    assert final["remote_id"] == remote_id


def test_publish_youtube_requires_intent_and_delegates_existing_uploader(tmp_path):
    uploader = _FakeYoutubeUploader()
    video = tmp_path / "short.mp4"
    video.write_bytes(b"video")
    receipt = tmp_path / "youtube.json"
    item = _intent_item()
    with pytest.raises(ny.PublicationBlocked, match="intent"):
        ny.publish_youtube(item, video, receipt_path=receipt, publish_at="2026-10-16T13:00:00+09:00", uploader_module=uploader)
    assert uploader.calls == []

    ny.prepare_intent(receipt, item=item, platform="youtube", account="운명과학TV")
    remote_id = ny.publish_youtube(item, video, receipt_path=receipt, publish_at="2026-10-16T13:00:00+09:00", uploader_module=uploader)
    assert remote_id == "youtube_123"
    assert uploader.calls[0]["publish_at"] == "2026-10-16T13:00:00+09:00"
    assert uploader.calls[0]["slot_hours"] == [13]
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "PUBLISHED"


class _Exec:
    def __init__(self, payload): self.payload = payload
    def execute(self): return self.payload


class _InsertReq:
    def next_chunk(self): return None, {"id": "yt_private_123"}


class _FakeYoutubeService:
    def __init__(self):
        self.insert_body = None
        self.insert_media = None

    def channels(self): return self
    def list(self, **kwargs): return _Exec({"items": [{"id": "UC_TEST_CHANNEL", "snippet": {"title": "운명과학TV"}}]})
    def videos(self): return self
    def insert(self, *, part, body, media_body):
        self.insert_body = body
        self.insert_media = media_body
        return _InsertReq()


class _FakePrivateUploaderModule:
    EXPECT_CHANNEL_TITLE = "운명과학TV"
    @staticmethod
    def _credentials(): return object()


def test_private_youtube_canary_has_no_publish_at(tmp_path):
    service = _FakeYoutubeService()
    video = tmp_path / "short.mp4"
    video.write_bytes(b"video")
    receipt = tmp_path / "youtube.json"
    item = _intent_item()
    ny.prepare_intent(receipt, item=item, platform="youtube_canary", account="운명과학TV")
    remote_id = ny.publish_youtube_private_canary(
        item,
        video,
        receipt_path=receipt,
        uploader_module=_FakePrivateUploaderModule,
        youtube_builder=lambda *a, **k: service,
        media_factory=lambda path, **kwargs: {"path": str(path), **kwargs},
    )
    assert remote_id == "yt_private_123"
    assert service.insert_body["status"]["privacyStatus"] == "private"
    assert "publishAt" not in service.insert_body["status"]
    assert service.insert_body["status"]["containsSyntheticMedia"] is True


def test_platform_failure_does_not_change_other_platform_receipt(tmp_path, monkeypatch):
    item = _intent_item()
    video = tmp_path / "short.mp4"
    video.write_bytes(b"video")
    yt_receipt = tmp_path / "youtube.json"
    th_receipt = tmp_path / "threads.json"
    ny.prepare_intent(yt_receipt, item=item, platform="youtube", account="운명과학TV")
    ny.publish_youtube(item, video, receipt_path=yt_receipt, publish_at="2026-10-16T13:00:00+09:00", uploader_module=_FakeYoutubeUploader())
    assert json.loads(yt_receipt.read_text(encoding="utf-8"))["status"] == "PUBLISHED"

    ny.prepare_intent(th_receipt, item=item, platform="threads", account="gsdo10042026")
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "token")
    with pytest.raises(RuntimeError, match="threads down"):
        ny.publish_threads_text(item, receipt_path=th_receipt, account="gsdo10042026", api_module=_FakeThreadsApi(fail=True), sleep_fn=lambda _: None)
    assert json.loads(yt_receipt.read_text(encoding="utf-8"))["status"] == "PUBLISHED"
    assert json.loads(th_receipt.read_text(encoding="utf-8"))["status"] == "PUBLISHING"


def test_render_short_uses_three_scenes_and_enforces_duration(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    bundle = tmp_path / "bundle"
    (bundle / "assets").mkdir(parents=True)
    Image.new("RGB", (800, 600), "white").save(bundle / "assets" / "001.jpg")
    item = {
        **_intent_item(),
        "asset": "assets/001.jpg",
        "format": "conclusion",
        "naver_title": "2027년 재물운 총정리",
        "summary_points": ["현금흐름을 먼저 봅니다.", "원국과 대운을 함께 봅니다.", "고정비를 점검합니다."],
        "shorts_script": "2027년 정미년 재물운은 원국과 대운, 재성의 연결을 함께 봐야 합니다. " * 4,
    }
    out = tmp_path / "short.mp4"
    commands = []

    def fake_tts(text, path):
        Path(path).write_bytes(b"a" * 2048)
        return {"engine": "fake"}

    class R:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"v" * 4096)
        return R()

    result = ny.render_short(item, bundle, out, tts_synth=fake_tts, command_runner=fake_run, probe_fn=lambda p: 32.0)
    assert out.exists()
    assert result["duration"] == 32.0
    assert result["scene_count"] == 3
    assert any("ffmpeg" in str(cmd[0]) for cmd in commands)


def test_render_short_blocks_out_of_range_narration(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    bundle = tmp_path / "bundle"
    (bundle / "assets").mkdir(parents=True)
    Image.new("RGB", (100, 100), "white").save(bundle / "assets" / "001.jpg")
    item = {**_intent_item(), "asset": "assets/001.jpg", "format": "conclusion", "naver_title": "2027 재물운", "summary_points": [], "shorts_script": "2027년 정미년 운세" * 20}

    def fake_tts(text, path):
        Path(path).write_bytes(b"a" * 2048)
        return {"engine": "fake"}

    with pytest.raises(ny.RenderBlocked, match="25-48"):
        ny.render_short(item, bundle, tmp_path / "out.mp4", tts_synth=fake_tts, command_runner=lambda *a, **k: None, probe_fn=lambda p: 49.0)



def test_render_short_allows_slightly_over_40_seconds(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    bundle = tmp_path / "bundle"
    (bundle / "assets").mkdir(parents=True)
    Image.new("RGB", (100, 100), "white").save(bundle / "assets" / "001.jpg")
    item = {**_intent_item(), "asset": "assets/001.jpg", "format": "conclusion", "naver_title": "2027 재물운", "summary_points": [], "shorts_script": "2027년 정미년 운세" * 20}
    out = tmp_path / "out.mp4"
    def fake_tts(text, path):
        Path(path).write_bytes(b"a" * 2048)
        return {"engine": "fake"}
    class R:
        returncode = 0
        stderr = ""
        stdout = ""
    def fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"v" * 4096)
        return R()
    result = ny.render_short(item, bundle, out, tts_synth=fake_tts, command_runner=fake_run, probe_fn=lambda p: 44.7)
    assert result["duration"] == 44.7

def test_private_canary_uses_separate_youtube_canary_publish_key(tmp_path):
    service = _FakeYoutubeService()
    video = tmp_path / "short.mp4"
    video.write_bytes(b"video")
    receipt = tmp_path / "youtube_canary.json"
    item = _intent_item()
    intent = ny.prepare_intent(receipt, item=item, platform="youtube_canary", account="운명과학TV")
    assert intent["publish_key"].endswith(":youtube_canary:운명과학TV")
    remote_id = ny.publish_youtube_private_canary(
        item,
        video,
        receipt_path=receipt,
        uploader_module=_FakePrivateUploaderModule,
        youtube_builder=lambda *a, **k: service,
        media_factory=lambda path, **kwargs: {"path": str(path), **kwargs},
    )
    assert remote_id == "yt_private_123"


def test_dispatch_dry_run_never_invokes_gh(tmp_path):
    post, _ = _post(tmp_path / "sources")
    item = ny.build_entry(post)
    manifest_path = tmp_path / "content.json"
    manifest_path.write_text(json.dumps({"items": [item]}, ensure_ascii=False), encoding="utf-8")

    def should_not_run(*args, **kwargs):
        raise AssertionError("gh must not run in dry-run")

    result = ny.dispatch_daily(
        date_iso="2026-10-16",
        manifest_path=manifest_path,
        source_root=post.parent,
        send=False,
        now=ny.datetime.fromisoformat("2026-10-16T15:30:00+09:00"),
        readiness_fn=lambda p: {"ready": True, "reasons": []},
        command_runner=should_not_run,
        lock_path=tmp_path / "fanout.lock",
        status_path=tmp_path / "status.jsonl",
    )
    assert result["action"] == "dry_run"


def test_dispatch_live_invokes_only_new_workflow_inside_safe_window(tmp_path):
    post, _ = _post(tmp_path / "sources")
    item = ny.build_entry(post)
    manifest_path = tmp_path / "content.json"
    manifest_path.write_text(json.dumps({"items": [item]}, ensure_ascii=False), encoding="utf-8")
    calls = []

    class R:
        returncode = 0
        stdout = "queued"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return R()

    result = ny.dispatch_daily(
        date_iso="2026-10-16",
        manifest_path=manifest_path,
        source_root=post.parent,
        send=True,
        now=ny.datetime.fromisoformat("2026-10-16T12:20:00+09:00"),
        readiness_fn=lambda p: {"ready": True, "reasons": []},
        command_runner=fake_run,
        lock_path=tmp_path / "fanout.lock",
        status_path=tmp_path / "status.jsonl",
        repo="gsdo1004-cloud/sajufortune-cards",
        workflow="newyear-2027-fanout.yml",
        dispatch_key="secret-key",
    )
    assert result["action"] == "dispatched"
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[:3] == ["gh", "workflow", "run"]
    assert "newyear-2027-fanout.yml" in cmd
    assert "date=2026-10-16" in cmd
    assert "send=true" in cmd
    assert not any("zodiac" in x.lower() for x in cmd)


def test_dispatch_live_blocks_after_1400_without_gh(tmp_path):
    post, _ = _post(tmp_path / "sources")
    item = ny.build_entry(post)
    manifest_path = tmp_path / "content.json"
    manifest_path.write_text(json.dumps({"items": [item]}, ensure_ascii=False), encoding="utf-8")
    calls = []
    result = ny.dispatch_daily(
        date_iso="2026-10-16",
        manifest_path=manifest_path,
        source_root=post.parent,
        send=True,
        now=ny.datetime.fromisoformat("2026-10-16T14:01:00+09:00"),
        readiness_fn=lambda p: {"ready": True, "reasons": []},
        command_runner=lambda *a, **k: calls.append(a),
        lock_path=tmp_path / "fanout.lock",
        status_path=tmp_path / "status.jsonl",
    )
    assert result["action"] == "hold"
    assert result["reason"] == "outside_safe_dispatch_window"
    assert calls == []


def test_new_workflow_is_dispatch_only_and_platform_isolated():
    workflow = Path(__file__).resolve().parent / ".github" / "workflows" / "newyear-2027-fanout.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "newyear-2027-fanout-${{ inputs.date }}" in text
    assert "threads:" in text
    assert "youtube:" in text
    assert "needs: gate" in text
    assert "needs: [gate, threads]" in text
    assert "always()" in text
    assert "youtube_canary" in text
    assert "newyear_2027/receipts" in text


def test_build_bundle_creates_deterministic_manifest_and_assets(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    source = tmp_path / "source"
    bundle = tmp_path / "bundle"
    for idx in range(1, 7):
        post, _ = _post(source, index=idx, slug=f"topic{idx}", publish_date=f"2026-10-{15+idx:02d}")
        (post / "images").mkdir()
        Image.new("RGB", (1600, 900), "white").save(post / "images" / "hero.png")
    manifest = ny.build_bundle(source, bundle, expected_count=6)
    assert manifest["schema"] == "newyear_2027/v1"
    assert len(manifest["items"]) == 6
    assert len({x["content_id"] for x in manifest["items"]}) == 6
    assert len({x["publish_date"] for x in manifest["items"]}) == 6
    assert [x["format"] for x in manifest["items"]] == list(ny.CONTENT_FORMATS)
    assert all(len(x["threads_text"]) <= 500 for x in manifest["items"])
    assert all("2027" in x["shorts_script"] for x in manifest["items"])
    assert all((bundle / x["asset"]).is_file() for x in manifest["items"])
    assert all(x.get("asset_sha256") for x in manifest["items"])
    saved = json.loads((bundle / "content.json").read_text(encoding="utf-8"))
    assert saved == manifest


def test_build_bundle_rejects_wrong_count_and_duplicate_dates(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    source = tmp_path / "source"
    for idx in range(1, 3):
        post, _ = _post(source, index=idx, slug=f"topic{idx}", publish_date="2026-10-16")
        (post / "images").mkdir()
        Image.new("RGB", (100, 100), "white").save(post / "images" / "hero.png")
    with pytest.raises(ValueError, match="expected 3 posts"):
        ny.build_bundle(source, tmp_path / "bundle_bad_count", expected_count=3)
    with pytest.raises(ValueError, match="duplicate publish_date"):
        ny.build_bundle(source, tmp_path / "bundle_dup", expected_count=2)


def test_build_bundle_rejects_missing_hero(tmp_path):
    source = tmp_path / "source"
    _post(source, index=1, slug="topic1", publish_date="2026-10-16")
    with pytest.raises(FileNotFoundError, match="hero"):
        ny.build_bundle(source, tmp_path / "bundle", expected_count=1)



def test_generated_copy_avoids_duplicate_2027_prefix_and_double_copula(tmp_path):
    for idx in range(1, 7):
        post, _ = _post(tmp_path, index=idx, slug=f"copy{idx}", publish_date=f"2026-11-{idx:02d}")
        entry = ny.build_entry(post)
        combined = entry["threads_text"] + "\n" + entry["shorts_script"]
        assert not re.search(r"2027년\s+2027년", combined)
        assert "입니다.’입니다" not in combined
        assert "입니다.'입니다" not in combined


def test_shorts_script_caps_long_source_copy_for_40s_margin():
    bullets = [
        "2027년 재물운은 돈이 생긴다 샌다보다 현금흐름과 계약 구조를 먼저 정리하는 해로 보는 것이 실용적입니다.",
        "재성이 보여도 일간이 감당할 힘과 식상 관성의 연결 그리고 현재 대운의 방향까지 함께 확인해야 합니다.",
        "가장 중요한 현실 점검은 고정비 부채 비상자금 계약 만기 세금 순서로 확인하는 것입니다.",
    ]
    article = "2027년 정미년은 원국과 대운, 재성, 일간의 힘을 함께 살펴야 실제 체감 흐름을 판단할 수 있습니다."
    script = ny._shorts_script("conclusion", "2027년 재물운 총정리｜핵심", bullets, article)
    assert 180 <= len(script) <= 300
    assert "2027" in script
    assert any(term in script for term in ("정미", "대운", "재성", "일간", "원국"))



def test_dispatch_permit_binds_date_content_hash_and_naver_url():
    item = _intent_item()
    item["publish_date"] = "2026-10-16"
    permit = ny.make_dispatch_permit("secret-key", item, "2026-10-16", "https://blog.naver.com/example/123")
    assert ny.verify_dispatch_permit("secret-key", item, "2026-10-16", "https://blog.naver.com/example/123", permit)
    assert not ny.verify_dispatch_permit("secret-key", item, "2026-10-17", "https://blog.naver.com/example/123", permit)
    assert not ny.verify_dispatch_permit("secret-key", item, "2026-10-16", "https://blog.naver.com/example/999", permit)


def test_dispatch_live_includes_signed_source_proof(tmp_path):
    post, _ = _post(tmp_path / "sources")
    item = ny.build_entry(post)
    manifest_path = tmp_path / "content.json"
    manifest_path.write_text(json.dumps({"items": [item]}, ensure_ascii=False), encoding="utf-8")
    calls = []
    class R:
        returncode = 0
        stdout = "queued"
        stderr = ""
    def fake_run(cmd, **kwargs):
        calls.append(list(cmd)); return R()
    result = ny.dispatch_daily(
        date_iso="2026-10-16", manifest_path=manifest_path, source_root=post.parent,
        send=True, now=ny.datetime.fromisoformat("2026-10-16T12:20:00+09:00"),
        readiness_fn=lambda p: {"ready": True, "reasons": []}, command_runner=fake_run,
        lock_path=tmp_path / "fanout.lock", status_path=tmp_path / "status.jsonl",
        dispatch_key="secret-key",
    )
    assert result["action"] == "dispatched"
    cmd = calls[0]
    source_args = [x for x in cmd if x.startswith("source_url=")]
    permit_args = [x for x in cmd if x.startswith("permit=")]
    assert source_args and source_args[0].startswith("source_url=https://")
    assert permit_args and len(permit_args[0].split("=",1)[1]) == 64


def test_normal_youtube_state_skips_when_private_canary_already_published(tmp_path):
    bundle = tmp_path / "bundle"
    receipt = ny._receipt_path(bundle, "2026-10-16", "youtube_canary")
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"status": "PUBLISHED", "remote_id": "private1"}), encoding="utf-8")
    action = ny.receipt_state(bundle, "2026-10-16", "youtube", block_if_platform="youtube_canary")
    assert action["action"] == "skip"
    assert action["reason"] == "blocked_by_youtube_canary"


def test_workflow_requires_signed_gate_before_platform_jobs():
    text = (Path(__file__).resolve().parent / ".github" / "workflows" / "newyear-2027-fanout.yml").read_text(encoding="utf-8")
    assert "permit:" in text
    assert "source_url:" in text
    assert "NEWYEAR_2027_DISPATCH_KEY" in text
    assert "verify-permit" in text
    assert "gate:" in text
    assert "needs: gate" in text
    assert "needs: [gate, threads]" in text
    assert "--block-if-platform youtube_canary" in text



def test_threads_fixed_user_id_mismatch_blocks_publish(tmp_path, monkeypatch):
    api = _FakeThreadsApi()
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "token")
    monkeypatch.setenv("THREADS_USER_ID", "expected-other-id")
    receipt = tmp_path / "threads.json"
    item = _intent_item()
    ny.prepare_intent(receipt, item=item, platform="threads", account="gsdo10042026")
    with pytest.raises(RuntimeError, match="Threads user id mismatch"):
        ny.publish_threads_text(item, receipt_path=receipt, account="gsdo10042026", api_module=api, sleep_fn=lambda _: None)
    assert api.calls == []


def test_private_canary_records_channel_identity(tmp_path):
    service = _FakeYoutubeService()
    video = tmp_path / "short.mp4"; video.write_bytes(b"video")
    receipt = tmp_path / "youtube_canary.json"
    item = _intent_item()
    ny.prepare_intent(receipt, item=item, platform="youtube_canary", account="운명과학TV")
    ny.publish_youtube_private_canary(
        item, video, receipt_path=receipt, uploader_module=_FakePrivateUploaderModule,
        youtube_builder=lambda *a, **k: service,
        media_factory=lambda path, **kwargs: {"path": str(path), **kwargs},
    )
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["channel_id"] == "UC_TEST_CHANNEL"
    assert data["channel_title"] == "운명과학TV"



def test_normal_youtube_fixed_channel_id_mismatch_blocks_before_upload(tmp_path, monkeypatch):
    class Uploader(_FakeYoutubeUploader):
        @staticmethod
        def _credentials(): return object()
    uploader = Uploader()
    service = _FakeYoutubeService()
    video = tmp_path / "short.mp4"; video.write_bytes(b"video")
    receipt = tmp_path / "youtube.json"
    item = _intent_item()
    ny.prepare_intent(receipt, item=item, platform="youtube", account="운명과학TV")
    monkeypatch.setenv("YOUTUBE_EXPECT_CHANNEL_ID", "UC_OTHER_CHANNEL")
    with pytest.raises(RuntimeError, match="channel id mismatch"):
        ny.publish_youtube(
            item, video, receipt_path=receipt, publish_at="2026-10-16T13:00:00+09:00",
            uploader_module=uploader, youtube_builder=lambda *a, **k: service,
        )
    assert uploader.calls == []
