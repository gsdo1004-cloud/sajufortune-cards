"""Untrusted-release and tampering tests; all fixtures synthetic in tmp_path, never published."""
import hashlib
import hmac
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import zodiac_publish_guard as gate
from scripts import zodiac_card_assets
from scripts import zodiac_mascot_atlas
from scripts import visual_quality_gate

DAY = "2026-12-07"
KEY = "synthetic-qa-only-do-not-use-in-production-" + "Z" * 38


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _sign(data, key=KEY):
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key.encode("utf-8"), raw, hashlib.sha256).hexdigest()


@pytest.fixture
def fake_styled(tmp_path, monkeypatch):
    root = tmp_path
    source = _write_json(root / "assets" / "flux_daily" / DAY / "manifest.json",
                         {"style_id": "STYLE_01", "date": DAY, "schema": "test-fixture-only"})
    atlas = _write_json(root / "assets" / "zodiac_mascot_atlas" / "STYLE_01" / "manifest.json",
                        {"style_id": "STYLE_01", "status": "PASS", "test_only": True})
    cards = []
    for i in range(1, 7):
        p = root / "cards" / DAY / f"card_{i:02d}.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((f"fake-card-{i}").encode())
        cards.append(p)
    video = root / "reels" / (DAY + "_tts.mp4")
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"fake-aac-tts-real-decoding-is-tested-elsewhere")
    monkeypatch.setattr(zodiac_card_assets, "verify", lambda day, root: cards)
    monkeypatch.setattr(zodiac_mascot_atlas, "atlas_dir",
                        lambda day, root: root / "assets" / "zodiac_mascot_atlas" / "STYLE_01")
    monkeypatch.setattr(zodiac_mascot_atlas, "verify_atlas", lambda day, root: {"status": "PASS"})
    def video_check(path, require_audio=False):
        assert require_audio is True
        return {"status": "PASS", "duration_seconds": 80.4,
                "sha256": gate.sha256(path)}
    monkeypatch.setattr(visual_quality_gate, "video_check", video_check)
    record = {
        "schema": "zodiac-signed-release-v1",
        "status": "APPROVED",
        "date": DAY,
        "style_id": "STYLE_01",
        "scopes": ["video", "cards"],
        "reviewer_id": "qa-synthetic-reviewer-only",
        "approved_at": "2026-11-23T10:00:00+09:00",
        "source_manifest_sha256": gate.sha256(source),
        "atlas_manifest_sha256": gate.sha256(atlas),
        "cards_sha256": {p.name: gate.sha256(p) for p in cards},
        "videos_sha256": {video.name: gate.sha256(video)},
        "avatar_and_voice_qa_status": "PASS",
    }
    record[gate.SIGNATURE_FIELD] = _sign(record)
    proof = _write_json(root / "assets" / "zodiac_release_approvals" / (DAY + ".json"), record)
    return SimpleNamespace(root=root, source=source, atlas=atlas, cards=cards,
                           video=video, proof=proof, approval=record)


def test_legacy_no_approval_keeps_existing_route_unchanged(tmp_path):
    assert gate.check(DAY, root=tmp_path)["status"] == "LEGACY_UNCHANGED"


def test_new_styled_without_review_evidence_blocks(tmp_path):
    _write_json(tmp_path/"assets"/"flux_daily"/DAY/"manifest.json", {"style_id": "STYLE_01"})
    with pytest.raises(gate.ReleaseHold):
        gate.check(DAY, root=tmp_path)


def test_missing_signed_review_blocks(fake_styled):
    fake_styled.proof.unlink()
    with pytest.raises(gate.ReleaseHold, match="RELEASE_ATTESTATION_MISSING_OR_INVALID"):
        gate.check(DAY, root=fake_styled.root, approval_key=KEY)


def test_no_real_key_holds_even_if_local_fake_fixture_is_signed(fake_styled, monkeypatch):
    monkeypatch.delenv(gate.APPROVAL_ENV, raising=False)
    with pytest.raises(gate.ReleaseHold, match="RELEASE_SIGNED_REVIEW_MISSING_OR_INVALID"):
        gate.check(DAY, root=fake_styled.root)


def test_synthetic_fixture_signed_video_only_inside_tmp_path(fake_styled):
    result = gate.check(DAY, root=fake_styled.root, approval_key=KEY)
    assert result["status"] == "VERIFIED_SIGNED_RELEASE"
    assert result["video_sha256"] == gate.sha256(fake_styled.video)


def test_synthetic_fixture_card_proof_inside_tmp_path(fake_styled):
    assert gate.check(DAY, root=fake_styled.root, mode="cards", approval_key=KEY)["mode"] == "cards"


def test_wrong_signature_key_holds(fake_styled):
    with pytest.raises(gate.ReleaseHold, match="RELEASE_SIGNED_REVIEW_MISSING_OR_INVALID"):
        gate.check(DAY, root=fake_styled.root, approval_key="W"*64)


def test_source_manifest_tamper_holds(fake_styled):
    fake_styled.source.write_text(fake_styled.source.read_text() + " ")
    with pytest.raises(gate.ReleaseHold, match="RELEASE_APPROVAL_PROVENANCE_MISMATCH"):
        gate.check(DAY, root=fake_styled.root, approval_key=KEY)


def test_video_tamper_holds(fake_styled):
    fake_styled.video.write_bytes(fake_styled.video.read_bytes() + b"changed")
    with pytest.raises(gate.ReleaseHold, match="RELEASE_VIDEO_SHA_UNAPPROVED"):
        gate.check(DAY, root=fake_styled.root, approval_key=KEY)


def test_card_tamper_holds(fake_styled):
    fake_styled.cards[2].write_bytes(b"changed-card")
    with pytest.raises(gate.ReleaseHold, match="RELEASE_APPROVAL_PROVENANCE_MISMATCH"):
        gate.check(DAY, root=fake_styled.root, approval_key=KEY)


def test_forged_reviewer_holds_even_if_attacker_edits_proof(fake_styled):
    d = json.loads(fake_styled.proof.read_text())
    d["reviewer_id"] = "self"
    d["hmac_sha256"] = _sign({k:v for k,v in d.items() if k != "hmac_sha256"})
    _write_json(fake_styled.proof, d)
    with pytest.raises(gate.ReleaseHold, match="RELEASE_APPROVAL_PROVENANCE_MISMATCH"):
        gate.check(DAY, root=fake_styled.root, approval_key=KEY)


def test_bad_date_and_video_path_rejected(fake_styled):
    with pytest.raises(gate.ReleaseHold, match="RELEASE_VIDEO_PATH_NOT_REELS"):
        gate.check(DAY, root=fake_styled.root, video="../somewhere.mp4", approval_key=KEY)


def test_missing_style_source_but_styled_layout_blocks(tmp_path):
    _write_json(tmp_path/"cards"/DAY/"layout_manifest.json", {"style_id":"STYLE_01"})
    with pytest.raises(gate.ReleaseHold, match="RELEASE_STYLED_ASSETS_WITHOUT_MANIFEST"):
        gate.check(DAY, root=tmp_path)


def test_style_downgrade_by_removing_style_id_is_detected(tmp_path):
    _write_json(tmp_path/"assets"/"flux_daily"/DAY/"manifest.json", {"date": DAY})
    _write_json(tmp_path/"cards"/DAY/"layout_manifest.json", {"style_id": "STYLE_01"})
    with pytest.raises(gate.ReleaseHold, match="RELEASE_STYLE_ID_DOWNGRADE_DETECTED"):
        gate.check(DAY, root=tmp_path)


class _Response:
    def __init__(self, data=b"approved", status_code=200):
        self._body, self.status_code = data, status_code
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def iter_content(self, _size): yield self._body


def test_remote_sha_positive_with_mocked_get_not_actual_network(monkeypatch):
    import requests
    called=[]
    def get(url, **kw):
        called.append((url,kw))
        return _Response()
    monkeypatch.setattr(requests,"get",get)
    url="https://raw.githubusercontent.com/gsdo1004-cloud/sajufortune-cards/main/reels/2026-12-07_tts.mp4"
    gate.verify_remote_sha(url, hashlib.sha256(b"approved").hexdigest())
    assert called and called[0][1]["allow_redirects"] is False


def test_remote_sha_mismatch_blocks_no_write(monkeypatch):
    import requests
    monkeypatch.setattr(requests,"get",lambda *a,**k:_Response(b"tampered"))
    with pytest.raises(gate.ReleaseHold, match="RELEASE_REMOTE_SHA_MISMATCH"):
        gate.verify_remote_sha(
            "https://raw.githubusercontent.com/gsdo1004-cloud/sajufortune-cards/main/reels/2026-12-07_tts.mp4",
            hashlib.sha256(b"approved").hexdigest())


@pytest.mark.parametrize("url",[
    "https://example.com/reels/a.mp4",
    "http://raw.githubusercontent.com/gsdo1004-cloud/sajufortune-cards/main/a",
    "https://raw.githubusercontent.com/attacker/sajufortune-cards/main/a",
])
def test_remote_url_cannot_downgrade_source(url):
    with pytest.raises(gate.ReleaseHold,match="RELEASE_REMOTE_URL_NOT_APPROVED"):
        gate.verify_remote_sha(url,"0"*64)


def test_instagram_styled_reel_never_contacts_api_without_proof(tmp_path, monkeypatch):
    import zodiac_instagram as ig
    from scripts import zodiac_publish_guard
    monkeypatch.setattr(ig,"BASE",tmp_path)
    monkeypatch.setattr(ig,"_skip_if_done",lambda *a:False)
    monkeypatch.setattr(zodiac_publish_guard,"styled_manifest",lambda *a:{"style_id":"STYLE_01"})
    def hold(*args,**kw): raise gate.ReleaseHold("MISSING_INDEPENDENT_APPROVAL")
    monkeypatch.setattr(zodiac_publish_guard,"check",hold)
    monkeypatch.setattr(ig,"publish_reel",lambda *a: (_ for _ in ()).throw(AssertionError("NETWORK_PUBLISH_MUST_NOT_RUN")))
    with pytest.raises(gate.ReleaseHold,match="MISSING_INDEPENDENT_APPROVAL"):
        ig.do_reel(DAY)


def test_threads_reel_never_contacts_api_without_proof(monkeypatch,tmp_path):
    import zodiac_reels as reels
    monkeypatch.setattr(reels,"BASE",tmp_path)
    from scripts import zodiac_publish_guard
    monkeypatch.setattr(zodiac_publish_guard,"check",lambda *a,**k:(_ for _ in ()).throw(gate.ReleaseHold("NO_SIGNED_PROOF")))
    monkeypatch.setattr(reels,"publish_video",lambda *a: (_ for _ in ()).throw(AssertionError("POST_MUST_NOT_RUN")))
    with pytest.raises(gate.ReleaseHold,match="NO_SIGNED_PROOF"):
        reels.do_publish(DAY)


def test_draft_workflows_have_guard_before_any_push_or_upload():
    root=Path(__file__).resolve().parent
    workflow=(root/".github/workflows/zodiac-cards.yml").read_text()
    assert workflow.index("FLUX seven-style release preflight") < workflow.index("커밋 (카드+릴스 public raw 호스팅)")
    assert workflow.index("python scripts/zodiac_publish_guard.py video \"$TODAY\"") < workflow.index('"youtube_upload.py"')
    # No cron changes are introduced by this test.
    threads=(root/".github/workflows/threads-zodiac-evening.yml").read_text()
    assert threads.index('python scripts/zodiac_publish_guard.py cards "$DI"') < threads.index('git add -A -- "cards/$DI"')
