import hashlib
import json
from pathlib import Path

import pytest

import newyear_2027_runner as ny


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _post(tmp_path: Path, *, index=1, slug="wealth", publish_date="2026-10-16") -> tuple[Path, str]:
    post = tmp_path / f"{index:02d}_{slug}"
    post.mkdir()
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
    assert 130 <= len(entry["shorts_script"]) <= 360


def test_build_entry_rotates_six_formats(tmp_path):
    formats = []
    for idx in range(1, 7):
        post, _ = _post(tmp_path, index=idx, slug=f"topic{idx}", publish_date=f"2026-10-{15+idx:02d}")
        formats.append(ny.build_entry(post)["format"])
    assert formats == list(ny.CONTENT_FORMATS)
    assert len(set(formats)) == 6
