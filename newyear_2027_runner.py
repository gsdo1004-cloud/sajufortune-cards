# -*- coding: utf-8 -*-
"""Independent 2027 new-year fortune fanout lane.

The module deliberately keeps the source gate/idempotency core independent from
existing today-fortune pipelines.  Remote publishing and scheduling are added by
later layers; the functions in this section are safe to exercise offline.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import tempfile
import time
import importlib.util
import sys
import uuid
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

CONTENT_FORMATS = (
    "conclusion",
    "checklist",
    "myth_break",
    "timing",
    "caution",
    "action",
)
EXPECTED_NAVER_CATEGORY = "2027 신년운세"


class PublicationBlocked(RuntimeError):
    """Raised when idempotency state makes an automatic publish unsafe."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def publication_payload_sha256(item: dict) -> str:
    """Digest the complete prebuilt publication manifest item.

    Runtime-only output_sha256 is intentionally excluded because it does not
    exist until the Short has been rendered.  All source-controlled copy,
    metadata, script, asset path/hash and transformation fields remain bound.
    """
    canonical = {k: v for k, v in dict(item).items() if k != "output_sha256"}
    raw = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _dispatch_message(
    item: dict,
    date_iso: str,
    source_url: str,
    mode: str,
    expires_at: str,
    payload_sha256: str,
    commit_sha: str,
) -> bytes:
    fields = [
        str(date_iso).strip(),
        str(item.get("content_id") or "").strip(),
        str(item.get("source_sha256") or "").strip(),
        str(source_url).strip(),
        str(mode).strip(),
        str(expires_at).strip(),
        str(payload_sha256).strip().lower(),
        str(commit_sha).strip().lower(),
    ]
    if not all(fields):
        raise ValueError("dispatch permit fields are incomplete")
    if fields[4] not in {"normal", "threads_canary", "youtube_private_canary"}:
        raise ValueError("invalid dispatch mode")
    if not re.fullmatch(r"[0-9a-f]{64}", fields[6]):
        raise ValueError("invalid payload digest")
    if not re.fullmatch(r"[0-9a-f]{40}", fields[7]):
        raise ValueError("invalid execution commit")
    return "\n".join(fields).encode("utf-8")


def make_dispatch_permit(
    key: str,
    item: dict,
    date_iso: str,
    source_url: str,
    mode: str,
    expires_at: str,
    payload_sha256: str,
    commit_sha: str,
) -> str:
    key = str(key or "").strip()
    if len(key) < 8:
        raise ValueError("dispatch key is missing or too short")
    return hmac.new(
        key.encode("utf-8"),
        _dispatch_message(
            item, date_iso, source_url, mode, expires_at, payload_sha256, commit_sha
        ),
        hashlib.sha256,
    ).hexdigest()


def verify_dispatch_permit(
    key: str,
    item: dict,
    date_iso: str,
    source_url: str,
    mode: str,
    expires_at: str,
    payload_sha256: str,
    commit_sha: str,
    permit: str,
) -> bool:
    try:
        expected = make_dispatch_permit(
            key, item, date_iso, source_url, mode, expires_at, payload_sha256, commit_sha
        )
    except Exception:
        return False
    return hmac.compare_digest(expected, str(permit or "").strip())


def validate_dispatch_authorization(
    key: str,
    item: dict,
    date_iso: str,
    source_url: str,
    mode: str,
    expires_at: str,
    payload_sha256: str,
    commit_sha: str,
    permit: str,
    *,
    now: datetime | None = None,
) -> dict:
    actual_payload = publication_payload_sha256(item)
    if not hmac.compare_digest(actual_payload, str(payload_sha256 or "").strip().lower()):
        return {"ok": False, "reason": "payload_digest_mismatch"}
    if not re.fullmatch(r"[0-9a-fA-F]{40}", str(commit_sha or "").strip()):
        return {"ok": False, "reason": "execution_commit_invalid"}
    if not verify_dispatch_permit(
        key, item, date_iso, source_url, mode, expires_at,
        actual_payload, str(commit_sha).lower(), permit,
    ):
        return {"ok": False, "reason": "permit_invalid"}
    try:
        expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return {"ok": False, "reason": "permit_expiry_invalid"}
    if expiry.tzinfo is None:
        return {"ok": False, "reason": "permit_expiry_invalid"}
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_utc = now_utc.astimezone(timezone.utc)
    expiry = expiry.astimezone(timezone.utc)
    if now_utc > expiry:
        return {"ok": False, "reason": "permit_expired"}
    if expiry > now_utc + timedelta(minutes=90):
        return {"ok": False, "reason": "permit_expiry_too_far"}
    now_kst = now_utc.astimezone(KST)
    if now_kst.date().isoformat() != str(date_iso):
        return {"ok": False, "reason": "remote_date_mismatch"}
    local_time = now_kst.time().replace(tzinfo=None)
    if mode == "youtube_private_canary":
        in_window = dt_time(8, 0) <= local_time <= dt_time(19, 0)
    else:
        in_window = dt_time(11, 0) <= local_time <= dt_time(14, 0)
    if not in_window:
        return {"ok": False, "reason": "outside_remote_window"}
    return {"ok": True, "reason": "authorized"}


def runtime_authorization_guard(
    item: dict,
    date_iso: str,
    mode: str,
    *,
    now_fn: Callable[[], datetime] | None = None,
) -> Callable[[str], None]:
    """Revalidate the signed permit at each remote side-effect boundary."""
    key = _load_dispatch_key()
    source_url = os.environ.get("SOURCE_URL_INPUT", "").strip()
    expires_at = os.environ.get("EXPIRES_AT_INPUT", "").strip()
    payload_sha256 = os.environ.get("PAYLOAD_SHA256_INPUT", "").strip()
    commit_sha = os.environ.get("COMMIT_SHA_INPUT", "").strip()
    permit = os.environ.get("DISPATCH_PERMIT_INPUT", "").strip()
    env_mode = os.environ.get("AUTH_MODE", "").strip()
    if env_mode != str(mode).strip():
        raise PublicationBlocked(f"runtime authorization mode mismatch: expected {mode}, got {env_mode or 'missing'}")
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def guard(stage: str) -> None:
        result = validate_dispatch_authorization(
            key, item, date_iso, source_url, mode, expires_at,
            payload_sha256, commit_sha, permit, now=now_fn(),
        )
        if not result.get("ok"):
            raise PublicationBlocked(
                f"runtime authorization failed at {stage}: {result.get('reason', 'unknown')}"
            )

    return guard


def _current_git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    sha = proc.stdout.strip().lower()
    if proc.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("current git commit is unavailable")
    return sha


def _resolve_remote_main_sha(repo: str, command_runner=None) -> str:
    command_runner = command_runner or subprocess.run
    proc = command_runner(
        ["gh", "api", f"repos/{repo}/commits/main", "--jq", ".sha"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    sha = str(getattr(proc, "stdout", "")).strip().lower()
    if getattr(proc, "returncode", 1) != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("remote main commit could not be resolved")
    return sha


def _load_dispatch_key(*, value: str | None = None, path: Path | None = None) -> str:
    key = str(value or os.environ.get("NEWYEAR_2027_DISPATCH_KEY", "")).strip()
    if not key and path is not None:
        try:
            key = Path(path).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            key = ""
    if len(key) < 8:
        raise RuntimeError("NEWYEAR_2027_DISPATCH_KEY is unavailable")
    return key


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _atomic_json_write(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_manifest(path: Path) -> dict:
    manifest = _read_json(Path(path))
    items = manifest.get("items")
    if not isinstance(items, list):
        raise ValueError("manifest.items must be a list")
    return manifest


def select_manifest_item(manifest: dict, date_iso: str) -> dict | None:
    items = manifest.get("items")
    if not isinstance(items, list):
        raise ValueError("manifest.items must be a list")
    matches = [item for item in items if isinstance(item, dict) and item.get("publish_date") == date_iso]
    if len(matches) > 1:
        raise ValueError(f"duplicate publish_date in manifest: {date_iso}")
    return matches[0] if matches else None


def validate_naver_receipt(path: Path) -> dict:
    """Accept only an unambiguous, RSS-confirmed Naver publish receipt."""
    path = Path(path)
    if not path.is_file():
        return {"ok": False, "reason": "naver_receipt_missing"}
    try:
        data = _read_json(path)
    except Exception:
        return {"ok": False, "reason": "naver_receipt_corrupt"}

    url = str(data.get("url") or "").strip()
    try:
        parsed_url = urlparse(url)
        valid_url = (
            parsed_url.scheme.lower() == "https"
            and (parsed_url.hostname or "").lower() in {"blog.naver.com", "m.blog.naver.com"}
            and parsed_url.username is None
            and parsed_url.password is None
        )
    except Exception:
        valid_url = False
    checks = (
        (data.get("success") is True, "naver_success_not_true"),
        (data.get("status") == "PUBLISHED", f"naver_status_{data.get('status') or 'missing'}"),
        (data.get("rss_seen") is True, "naver_rss_not_confirmed"),
        (bool(url), "naver_url_missing"),
        (valid_url, "naver_url_invalid"),
        (data.get("category") == EXPECTED_NAVER_CATEGORY, "naver_category_mismatch"),
        (bool(re.fullmatch(r"[0-9a-f]{64}", str(data.get("source_sha256") or ""))), "naver_source_hash_missing"),
        (bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data.get("publish_date") or ""))), "naver_publish_date_missing"),
    )
    for passed, reason in checks:
        if not passed:
            return {"ok": False, "reason": reason, "status": data.get("status", "")}
    return {
        "ok": True,
        "reason": "published_confirmed",
        "url": url,
        "published_at": data.get("published_at", ""),
        "source_sha256": str(data.get("source_sha256") or ""),
        "publish_date": str(data.get("publish_date") or ""),
        "source_dir": str(data.get("source_dir") or ""),
    }


def _safe_child(root: Path, child_name: str) -> Path:
    root = Path(root).resolve()
    child = (root / child_name).resolve()
    try:
        child.relative_to(root)
    except ValueError as exc:
        raise ValueError("source_dir escapes source_root") from exc
    return child


def source_gate(
    item: dict,
    source_root: Path,
    *,
    readiness_fn: Callable[[Path], dict] | None = None,
) -> dict:
    """Read-only source gate for the local dispatcher.

    `readiness_fn` is dependency-injected so the production dispatcher can call
    the existing Naver publisher's read-only `readiness()` without copying or
    mutating that project.
    """
    source_dir = str(item.get("source_dir") or "").strip()
    if not source_dir:
        return {"ok": False, "reason": "source_dir_missing"}
    try:
        post_dir = _safe_child(Path(source_root), source_dir)
    except ValueError:
        return {"ok": False, "reason": "source_dir_invalid"}

    article = post_dir / "article.md"
    meta_path = post_dir / "meta.json"
    if not article.is_file() or not meta_path.is_file():
        return {"ok": False, "reason": "source_files_missing"}

    try:
        meta = _read_json(meta_path)
    except Exception:
        return {"ok": False, "reason": "source_meta_corrupt"}

    if meta.get("publish_date") != item.get("publish_date"):
        return {"ok": False, "reason": "source_publish_date_mismatch"}
    expected_sha = str(item.get("source_sha256") or "")
    if not expected_sha or _sha256(article) != expected_sha:
        return {"ok": False, "reason": "source_hash_mismatch"}

    if readiness_fn is not None:
        try:
            readiness = readiness_fn(post_dir)
        except Exception as exc:
            return {"ok": False, "reason": f"source_readiness_error:{type(exc).__name__}"}
        if not isinstance(readiness, dict) or readiness.get("ready") is not True:
            reasons = readiness.get("reasons", []) if isinstance(readiness, dict) else []
            suffix = ",".join(str(x) for x in reasons) or "not_ready"
            return {"ok": False, "reason": f"source_readiness_blocked:{suffix}"}

    receipt = validate_naver_receipt(post_dir / "naver_publish.json")
    if not receipt.get("ok"):
        return {"ok": False, "reason": receipt.get("reason", "naver_receipt_blocked")}
    if receipt.get("source_sha256") != expected_sha:
        return {"ok": False, "reason": "naver_receipt_source_hash_mismatch"}
    if receipt.get("publish_date") != item.get("publish_date"):
        return {"ok": False, "reason": "naver_receipt_publish_date_mismatch"}
    if receipt.get("source_dir") and receipt.get("source_dir") != source_dir:
        return {"ok": False, "reason": "naver_receipt_source_dir_mismatch"}
    return {"ok": True, "reason": "ready_and_naver_published", "post_dir": str(post_dir), "naver_url": receipt["url"]}


class OwnedFileLock:
    """Exclusive file lock that can never unlink a lock it did not acquire."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.owner = uuid.uuid4().hex
        self.acquired = False

    def __enter__(self) -> "OwnedFileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            payload = {"owner": self.owner, "pid": os.getpid(), "created_at": _now_iso()}
            os.write(fd, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        finally:
            os.close(fd)
        self.acquired = True
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self.acquired:
            return False
        try:
            current = _read_json(self.path)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            current = {}
        if current.get("owner") == self.owner:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self.acquired = False
        return False


def _publish_key(content_id: str, platform: str, account: str) -> str:
    if not content_id or not platform or not account:
        raise ValueError("content_id, platform and account are required")
    return f"{content_id}:{platform}:{account}"


def prepare_intent(receipt_path: Path, *, item: dict, platform: str, account: str) -> dict:
    """Persist PUBLISHING before a remote side effect.

    Any existing state blocks automation.  This intentionally prefers a safe
    HOLD over a possible duplicate when the previous process outcome is unknown.
    """
    receipt_path = Path(receipt_path)
    if receipt_path.exists():
        try:
            existing = _read_json(receipt_path)
            status = str(existing.get("status") or "UNKNOWN")
        except Exception:
            status = "CORRUPT"
        raise PublicationBlocked(f"existing publication receipt is {status}")

    data = {
        "status": "PUBLISHING",
        "publish_key": _publish_key(str(item.get("content_id") or ""), platform, account),
        "content_id": item.get("content_id"),
        "platform": platform,
        "account": account,
        "source_sha256": item.get("source_sha256", ""),
        "output_sha256": item.get("output_sha256", ""),
        "owner_token": uuid.uuid4().hex,
        "started_at": _now_iso(),
    }
    _atomic_json_write(receipt_path, data)
    return data


def finalize_receipt(receipt_path: Path, *, remote_id: str, extra: dict | None = None) -> dict:
    receipt_path = Path(receipt_path)
    if not remote_id:
        raise ValueError("remote_id is required")
    if not receipt_path.is_file():
        raise PublicationBlocked("publication intent is missing")
    try:
        data = _read_json(receipt_path)
    except Exception as exc:
        raise PublicationBlocked("publication intent is corrupt") from exc
    if data.get("status") != "PUBLISHING":
        raise PublicationBlocked(f"cannot finalize state {data.get('status') or 'UNKNOWN'}")
    data.update(extra or {})
    data.update({"status": "PUBLISHED", "remote_id": remote_id, "finished_at": _now_iso()})
    _atomic_json_write(receipt_path, data)
    return data


def validate_durable_receipt_transition(action: str, current: dict | None, incoming: dict) -> dict:
    """Validate main-branch durable receipt transitions before copying state.

    claim: durable path must not exist and incoming must be PUBLISHING.
    finalize: durable state must be the same PUBLISHING claim and incoming PUBLISHED.
    """
    if action not in {"claim", "finalize"}:
        return {"ok": False, "reason": "invalid_transition_action"}
    if not isinstance(incoming, dict):
        return {"ok": False, "reason": "incoming_receipt_invalid"}
    if action == "claim":
        if current is not None:
            return {"ok": False, "reason": "durable_receipt_exists"}
        if incoming.get("status") != "PUBLISHING":
            return {"ok": False, "reason": "incoming_not_publishing"}
        if not re.fullmatch(r"[0-9a-f]{32}", str(incoming.get("owner_token") or "")):
            return {"ok": False, "reason": "owner_token_invalid"}
        return {"ok": True, "reason": "claim_allowed"}

    if current is None:
        return {"ok": False, "reason": "durable_receipt_missing"}
    if current.get("status") != "PUBLISHING":
        return {"ok": False, "reason": f"durable_state_{current.get('status') or 'UNKNOWN'}"}
    if incoming.get("status") != "PUBLISHED":
        return {"ok": False, "reason": "incoming_not_published"}
    for field in ("publish_key", "content_id", "platform", "account", "source_sha256", "output_sha256", "owner_token"):
        if str(current.get(field) or "") != str(incoming.get(field) or ""):
            return {"ok": False, "reason": f"receipt_{field}_mismatch"}
    if not str(incoming.get("remote_id") or "").strip():
        return {"ok": False, "reason": "remote_id_missing"}
    return {"ok": True, "reason": "finalize_allowed"}


def validate_durable_receipt_owner(durable: dict, local: dict) -> dict:
    """Require remote main receipt to be exactly owned by this local run."""
    if not isinstance(durable, dict) or not isinstance(local, dict):
        return {"ok": False, "reason": "receipt_invalid"}
    if durable.get("status") != local.get("status"):
        return {"ok": False, "reason": "receipt_status_mismatch"}
    for field in (
        "publish_key", "content_id", "platform", "account",
        "source_sha256", "output_sha256", "owner_token",
    ):
        if str(durable.get(field) or "") != str(local.get(field) or ""):
            return {"ok": False, "reason": f"receipt_{field}_mismatch"}
    owner = str(local.get("owner_token") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", owner):
        return {"ok": False, "reason": "owner_token_invalid"}
    if local.get("status") == "PUBLISHED":
        if str(durable.get("remote_id") or "") != str(local.get("remote_id") or ""):
            return {"ok": False, "reason": "receipt_remote_id_mismatch"}
    return {"ok": True, "reason": "durable_owner_confirmed"}


def _meta_index(meta: dict, post_dir: Path) -> int:
    raw = meta.get("index")
    try:
        if raw is not None:
            return int(raw)
    except (TypeError, ValueError):
        pass
    m = re.match(r"^(\d+)", post_dir.name)
    if not m:
        raise ValueError(f"post index missing: {post_dir.name}")
    return int(m.group(1))


def _slug(meta: dict, post_dir: Path) -> str:
    slug = str(meta.get("slug") or "").strip()
    if not slug:
        slug = re.sub(r"^\d+_?", "", post_dir.name).strip()
    slug = re.sub(r"[^0-9A-Za-z_-]+", "-", slug).strip("-")
    return slug or f"post-{_meta_index(meta, post_dir):03d}"


def _clean_markdown(text: str) -> str:
    text = re.sub(r"\[\[IMAGE:[^\]]+\]\]", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_>#]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_summary_bullets(article: str) -> list[str]:
    lines = article.splitlines()
    in_summary = False
    bullets: list[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^##\s*30초\s*핵심\s*요약", stripped):
            in_summary = True
            continue
        if in_summary and stripped.startswith("##"):
            break
        if in_summary and re.match(r"^[-*]\s+", stripped):
            val = _clean_markdown(re.sub(r"^[-*]\s+", "", stripped))
            if val:
                bullets.append(val)
    if bullets:
        return bullets[:3]

    plain = _clean_markdown(article)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?다요])\s+", plain) if len(s.strip()) >= 18]
    return sentences[:3]


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip(" ,.:;!?") + "…"


def _title_core(title: str) -> str:
    core = re.split(r"[｜|]", title, maxsplit=1)[0].strip()
    core = re.sub(r"^2027년\s+", "", core).strip()
    return _clip(core or "신년운세", 46)


def _threads_text(fmt: str, title: str, bullets: list[str]) -> str:
    b1 = _clip(bullets[0] if bullets else "2027년 운은 결과보다 흐름을 먼저 봐야 합니다.", 78)
    b2 = _clip(bullets[1] if len(bullets) > 1 else "원래 사주와 현재 대운을 함께 봐야 판단이 선명해집니다.", 78)
    b3 = _clip(bullets[2] if len(bullets) > 2 else "지금 바꿀 수 있는 한 가지 행동부터 점검하세요.", 72)
    core = _title_core(title)

    templates = {
        "conclusion": (
            f"2027년 {core}, 결론부터 보면 이렇습니다.\n"
            f"{b1}\n"
            "그런데 결과보다 먼저 확인할 순서가 있습니다.\n\n"
            f"핵심은 {b2}\n{b3}\n\n몇 년생/어떤 상황인지 댓글로 남기고, 연말에 다시 보려면 저장해 두세요."
        ),
        "checklist": (
            f"2027년 {core}, 이것부터 체크하세요.\n"
            "좋다·나쁘다보다 놓치기 쉬운 한 가지가 더 중요합니다.\n\n"
            f"① {b1}\n② {b2}\n③ {b3}\n\n지금 해당되는 항목을 댓글에 적어보고, 체크용으로 저장해 두세요."
        ),
        "myth_break": (
            f"2027년 {core}, ‘운만 좋으면 된다’고 보면 놓칩니다.\n"
            "같은 운도 준비 상태에 따라 결과가 달라집니다.\n\n"
            f"먼저 볼 것: {b1}\n그다음: {b2}\n실행: {b3}\n\n공감되는 부분을 댓글로 남기고 저장해 두세요."
        ),
        "timing": (
            f"2027년 {core}, 타이밍보다 먼저 볼 게 있습니다.\n"
            "언제 움직일지보다 ‘무엇을 정리한 뒤 움직일지’가 핵심입니다.\n\n"
            f"기준은 {b1}\n그리고 {b2}\n마지막으로 {b3}\n\n올해 꼭 확인할 항목이라면 저장하고, 궁금한 점은 댓글로 남겨보세요."
        ),
        "caution": (
            f"2027년 {core}, 이 부분은 서두르지 마세요.\n"
            "운이 들어와도 구조가 약하면 체감 결과가 달라질 수 있습니다.\n\n"
            f"주의점: {b1}\n확인점: {b2}\n대응: {b3}\n\n비슷한 고민이 있다면 댓글로 남기고, 결정 전에 다시 보도록 저장하세요."
        ),
        "action": (
            f"2027년 {core}, 오늘 할 일은 하나입니다.\n"
            "운세를 읽고 끝내지 말고 바꿀 수 있는 행동으로 연결하세요.\n\n"
            f"먼저 {b1}\n그다음 {b2}\n실행은 {b3}\n\n오늘 하나 실천했다면 댓글에 남기고, 다음 점검을 위해 저장해 두세요."
        ),
    }
    text = templates[fmt]
    if len(text) > 500:
        # Keep the native line structure and CTA while trimming source bullets first.
        text = text.replace(b1, _clip(b1, 54)).replace(b2, _clip(b2, 54)).replace(b3, _clip(b3, 48))
    if len(text) > 500:
        # Templates are sized to stay below this, but fail closed without flattening newlines.
        text = text[:499].rstrip() + "…"
    return text


def _shorts_script(fmt: str, title: str, bullets: list[str], article: str) -> str:
    core = _title_core(title)
    b1 = _clip(bullets[0] if bullets else "결과보다 흐름과 준비 상태를 먼저 점검하세요", 44)
    b2 = _clip(bullets[1] if len(bullets) > 1 else "원래 사주와 현재 대운을 함께 봐야 합니다", 44)
    b3 = _clip(bullets[2] if len(bullets) > 2 else "지금 바꿀 수 있는 행동 한 가지부터 정리하세요", 38)
    basis = "2027년 정미년은 같은 기운도 원국과 대운, 일간의 힘에 따라 체감이 달라집니다."
    # Prefer an explicit source sentence when it carries useful 명리 vocabulary.
    plain = _clean_markdown(article)
    candidates = [s.strip() for s in re.split(r"(?<=[.!?다요])\s+", plain)
                  if any(t in s for t in ("정미", "명리", "대운", "재성", "일간", "원국", "오행"))]
    if candidates:
        basis = _clip(candidates[0], 54)

    openers = {
        "conclusion": f"2027년 {core}, 결론부터 말씀드리겠습니다.",
        "checklist": f"2027년 {core}, 세 가지만 체크해 보세요.",
        "myth_break": f"2027년 {core}, 운만 좋으면 된다는 생각은 위험합니다.",
        "timing": f"2027년 {core}, 움직이는 시기보다 먼저 볼 것이 있습니다.",
        "caution": f"2027년 {core}, 이 부분은 서두르지 마세요.",
        "action": f"2027년 {core}, 오늘 바꿀 행동 한 가지를 정해보세요.",
    }
    closers = {
        "conclusion": "핵심은 결과를 기다리기보다 준비 순서를 바로잡는 것입니다.",
        "checklist": "세 항목 중 하나라도 걸린다면 먼저 정리하고 움직이세요.",
        "myth_break": "운의 이름보다 내 구조와 선택이 연결되는지를 확인하세요.",
        "timing": "준비가 끝난 뒤 타이밍을 잡아야 좋은 흐름을 실제 결과로 연결할 수 있습니다.",
        "caution": "좋은 신호가 보여도 확인 없이 크게 움직이는 선택은 피하는 편이 좋습니다.",
        "action": "오늘 할 수 있는 한 가지를 정리하면 운세가 행동 계획으로 바뀝니다.",
    }
    return (
        f"{openers[fmt]} {basis} "
        f"첫째, {b1} 둘째, {b2} 셋째, {b3} "
        f"{closers[fmt]} 2027 운세는 저장하고 다음 편도 확인하세요."
    )


def build_entry(post_dir: Path) -> dict:
    post_dir = Path(post_dir)
    meta = _read_json(post_dir / "meta.json")
    article_path = post_dir / "article.md"
    article = article_path.read_text(encoding="utf-8")
    index = _meta_index(meta, post_dir)
    slug = _slug(meta, post_dir)
    fmt = CONTENT_FORMATS[(index - 1) % len(CONTENT_FORMATS)]
    title = str(meta.get("naver_title") or meta.get("title") or "2027년 신년운세").strip()
    bullets = _extract_summary_bullets(article)
    source_url = str(meta.get("source_url") or "").strip()
    content_id = f"ny2027-{index:03d}-{slug}"
    script = _shorts_script(fmt, title, bullets, article)
    return {
        "content_id": content_id,
        "index": index,
        "slug": slug,
        "format": fmt,
        "publish_date": str(meta.get("publish_date") or ""),
        "source_dir": post_dir.name,
        "source_sha256": _sha256(article_path),
        "source_url": source_url,
        "naver_title": title,
        "threads_text": _threads_text(fmt, title, bullets),
        "shorts_script": script,
        "youtube_title": _clip(f"{_title_core(title)} #2027운세 #신년운세", 100),
        "youtube_description": _clip(
            f"2027년 정미년 운세 핵심을 짧게 정리했습니다. 원문: {source_url} "
            "개인 사주는 원국과 대운에 따라 달라질 수 있습니다.",
            4900,
        ),
        "tags": ["2027운세", "2027년운세", "신년운세", "정미년", "운명과학TV"],
        "summary_points": bullets,
        "asset": f"assets/{index:03d}.jpg",
    }


class RenderBlocked(RuntimeError):
    """Raised when a Short does not satisfy the publish-quality contract."""


def _require_intent(receipt_path: Path, *, item: dict, platform: str, account: str) -> dict:
    receipt_path = Path(receipt_path)
    if not receipt_path.is_file():
        raise PublicationBlocked("publication intent is missing")
    try:
        data = _read_json(receipt_path)
    except Exception as exc:
        raise PublicationBlocked("publication intent is corrupt") from exc
    if data.get("status") != "PUBLISHING":
        raise PublicationBlocked(f"publication intent state is {data.get('status') or 'UNKNOWN'}")
    expected = _publish_key(str(item.get("content_id") or ""), platform, account)
    if data.get("publish_key") != expected:
        raise PublicationBlocked("publication intent key mismatch")
    return data


def publish_threads_text(
    item: dict,
    *,
    receipt_path: Path,
    account: str = "gsdo10042026",
    api_module=None,
    sleep_fn=time.sleep,
    authorization_guard: Callable[[str], None] | None = None,
) -> str:
    """Publish one text-only Threads post after a durable intent exists."""
    _require_intent(receipt_path, item=item, platform="threads", account=account)
    if api_module is None:
        import zodiac_cardnews as api_module

    token = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("THREADS_ACCESS_TOKEN is missing")
    uid = api_module._threads_uid(token)
    configured_uid = os.environ.get("THREADS_USER_ID", "").strip()
    if configured_uid and configured_uid != str(uid):
        raise RuntimeError(f"Threads user id mismatch: expected {configured_uid}, got {uid}")
    base = f"https://graph.threads.net/v1.0/{uid}"
    if authorization_guard is not None:
        authorization_guard("before_create")
    created = api_module._post(
        f"{base}/threads",
        {"media_type": "TEXT", "text": str(item.get("threads_text") or ""), "access_token": token},
    )
    creation_id = created.get("id") if isinstance(created, dict) else None
    if not creation_id:
        raise RuntimeError(f"Threads container creation failed: {created}")
    sleep_fn(2)
    if authorization_guard is not None:
        authorization_guard("before_publish")
    published = api_module._post(
        f"{base}/threads_publish",
        {"creation_id": creation_id, "access_token": token},
    )
    remote_id = published.get("id") if isinstance(published, dict) else None
    if not remote_id:
        raise RuntimeError(f"Threads publish failed: {published}")
    finalize_receipt(receipt_path, remote_id=str(remote_id), extra={"creation_id": str(creation_id)})
    return str(remote_id)


def publish_youtube(
    item: dict,
    video: Path,
    *,
    receipt_path: Path,
    publish_at: str,
    uploader_module=None,
    youtube_builder=None,
    authorization_guard: Callable[[str], None] | None = None,
) -> str:
    """Use the existing channel-locking YouTube uploader for normal publication."""
    account = "운명과학TV"
    _require_intent(receipt_path, item=item, platform="youtube", account=account)
    video = Path(video)
    if not video.is_file():
        raise FileNotFoundError(video)
    if uploader_module is None:
        import youtube_upload as uploader_module
    expected_channel_id = os.environ.get("YOUTUBE_EXPECT_CHANNEL_ID", "").strip()
    if expected_channel_id:
        creds = uploader_module._credentials()
        if not creds:
            raise RuntimeError("YouTube credentials are unavailable")
        if youtube_builder is None:
            from googleapiclient.discovery import build as youtube_builder
        youtube = youtube_builder("youtube", "v3", credentials=creds)
        me = youtube.channels().list(part="snippet", mine=True).execute()
        items = me.get("items") or []
        if not items:
            raise RuntimeError("YouTube channel lookup returned no channel")
        actual_id = str(items[0].get("id") or "").strip()
        actual_title = str(items[0].get("snippet", {}).get("title") or "").strip()
        expected_title = str(getattr(uploader_module, "EXPECT_CHANNEL_TITLE", account) or account).strip()
        if expected_title and actual_title != expected_title:
            raise RuntimeError(f"YouTube channel mismatch: expected {expected_title}, got {actual_title or 'unknown'}")
        if actual_id != expected_channel_id:
            raise RuntimeError(f"YouTube channel id mismatch: expected {expected_channel_id}, got {actual_id or 'unknown'}")
    if authorization_guard is not None:
        authorization_guard("before_upload")
    remote_id = uploader_module.upload(
        video=video,
        title=str(item.get("youtube_title") or "2027년 신년운세"),
        description=str(item.get("youtube_description") or ""),
        tags=list(item.get("tags") or []),
        publish_at=publish_at,
        slot_hours=[13],
        thumbnail=None,
        authorization_guard=authorization_guard,
    )
    if not remote_id:
        raise RuntimeError("YouTube upload returned no video id")
    finalize_receipt(receipt_path, remote_id=str(remote_id), extra={"publish_at": publish_at, "private_canary": False})
    return str(remote_id)


def publish_youtube_private_canary(
    item: dict,
    video: Path,
    *,
    receipt_path: Path,
    uploader_module=None,
    youtube_builder=None,
    media_factory=None,
    authorization_guard: Callable[[str], None] | None = None,
) -> str:
    """Upload a true private canary: privacy=private and no publishAt field."""
    account = "운명과학TV"
    _require_intent(receipt_path, item=item, platform="youtube_canary", account=account)
    video = Path(video)
    if not video.is_file():
        raise FileNotFoundError(video)
    if uploader_module is None:
        import youtube_upload as uploader_module
    creds = uploader_module._credentials()
    if not creds:
        raise RuntimeError("YouTube credentials are unavailable")
    if youtube_builder is None:
        from googleapiclient.discovery import build as youtube_builder
    if media_factory is None:
        from googleapiclient.http import MediaFileUpload as media_factory

    youtube = youtube_builder("youtube", "v3", credentials=creds)
    me = youtube.channels().list(part="snippet", mine=True).execute()
    items = me.get("items") or []
    if not items:
        raise RuntimeError("YouTube channel lookup returned no channel")
    actual_channel_id = str(items[0].get("id") or "").strip()
    actual_title = str(items[0].get("snippet", {}).get("title") or "").strip()
    expected_title = str(getattr(uploader_module, "EXPECT_CHANNEL_TITLE", account) or account).strip()
    expected_channel_id = os.environ.get("YOUTUBE_EXPECT_CHANNEL_ID", "").strip()
    if expected_title and actual_title != expected_title:
        raise RuntimeError(f"YouTube channel mismatch: expected {expected_title}, got {actual_title or 'unknown'}")
    if expected_channel_id and actual_channel_id != expected_channel_id:
        raise RuntimeError(f"YouTube channel id mismatch: expected {expected_channel_id}, got {actual_channel_id or 'unknown'}")

    body = {
        "snippet": {
            "title": str(item.get("youtube_title") or "2027년 신년운세")[:100],
            "description": str(item.get("youtube_description") or "")[:4900],
            "tags": list(item.get("tags") or [])[:30],
            "categoryId": "24",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }
    media = media_factory(str(video), mimetype="video/mp4", chunksize=-1, resumable=True)
    if authorization_guard is not None:
        authorization_guard("before_insert")
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        if authorization_guard is not None:
            authorization_guard("before_chunk")
        _status, response = req.next_chunk()
    remote_id = response.get("id") if isinstance(response, dict) else None
    if not remote_id:
        raise RuntimeError("YouTube private canary returned no video id")
    finalize_receipt(
        receipt_path,
        remote_id=str(remote_id),
        extra={
            "private_canary": True,
            "publish_at": None,
            "channel_id": actual_channel_id,
            "channel_title": actual_title,
            "promotion_policy": "never_auto_promote",
        },
    )
    return str(remote_id)


def _synthesize_free(text: str, out_mp3: Path) -> dict:
    """Free-first TTS: local Supertonic, then free Edge. Never Typecast."""
    try:
        import tts_supertonic
        if tts_supertonic.synth(text, out_mp3, speed=1.30):
            return {"engine": "supertonic", "voice": getattr(tts_supertonic, "VOICE", "M2")}
    except Exception:
        pass
    import typecast_tts
    typecast_tts.synth_edge(text, out_mp3, tempo=1.25)
    return {"engine": "edge", "voice": typecast_tts.EDGE_VOICE}


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 0:
        raise RenderBlocked(f"ffprobe failed: {result.stderr[-300:]}")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise RenderBlocked("ffprobe returned invalid duration") from exc


def _font_path() -> str | None:
    candidates = [
        os.environ.get("NEWYEAR_2027_FONT", ""),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        r"C:\Windows\Fonts\malgunbd.ttf",
        r"C:\Windows\Fonts\malgun.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def _wrap_caption(text: str, width: int = 18) -> str:
    words = str(text).strip().split()
    if not words:
        return ""
    lines: list[str] = []
    current = ""
    for word in words:
        proposed = word if not current else f"{current} {word}"
        if len(proposed) <= width:
            current = proposed
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\n".join(lines[:5])


def _visual_captions(item: dict) -> list[str]:
    points = [str(x).strip() for x in item.get("summary_points", []) if str(x).strip()]
    while len(points) < 2:
        points.append("원국과 대운을 함께 확인하세요.")
    title = _title_core(str(item.get("naver_title") or "2027년 신년운세"))
    return [
        f"{title}\n결론부터 확인하세요",
        _clip(points[0], 62),
        f"{_clip(points[1], 52)}\n저장하고 다음 편도 확인하세요",
    ]


def _render_scene(asset: Path, caption: str, out_path: Path, *, scene_no: int) -> None:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

    with Image.open(asset) as src:
        src = ImageOps.exif_transpose(src).convert("RGB")
        background = ImageOps.fit(src, (1080, 1920), method=Image.Resampling.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(20))
        background = ImageEnhance.Brightness(background).enhance(0.38)
        main = ImageOps.contain(src, (900, 760), method=Image.Resampling.LANCZOS)
        canvas = background.copy()

    x = (1080 - main.width) // 2
    y = 210 + max(0, (760 - main.height) // 2)
    canvas.paste(main, (x, y))
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rounded_rectangle((60, 1080, 1020, 1810), radius=48, fill=(0, 0, 0, 190))
    font_path = _font_path()
    try:
        label_font = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()
        body_font = ImageFont.truetype(font_path, 68) if font_path else ImageFont.load_default()
    except OSError:
        label_font = body_font = ImageFont.load_default()
    draw.text((100, 1135), f"2027 신년운세 · {scene_no}/3", font=label_font, fill=(255, 255, 255, 215))
    wrapped = _wrap_caption(caption, 17)
    box = draw.multiline_textbbox((0, 0), wrapped, font=body_font, spacing=20, align="center")
    tw = box[2] - box[0]
    th = box[3] - box[1]
    draw.multiline_text(((1080 - tw) / 2, 1400 - th / 2), wrapped, font=body_font, spacing=20, align="center", fill="white")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, quality=92, optimize=True)


def render_short(
    item: dict,
    bundle_root: Path,
    out_path: Path,
    *,
    tts_synth=None,
    command_runner=None,
    probe_fn=None,
) -> dict:
    """Render an isolated three-scene vertical Short and enforce 25–48 seconds."""
    bundle_root = Path(bundle_root)
    out_path = Path(out_path)
    asset = _safe_child(bundle_root, str(item.get("asset") or ""))
    if not asset.is_file():
        raise RenderBlocked(f"asset missing: {asset}")
    script = str(item.get("shorts_script") or "").strip()
    if not script:
        raise RenderBlocked("shorts_script is empty")
    tts_synth = tts_synth or _synthesize_free
    command_runner = command_runner or subprocess.run
    probe_fn = probe_fn or _probe_duration

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ny2027-render-") as tmp_name:
        tmp = Path(tmp_name)
        audio = tmp / "narration.mp3"
        tts_meta = tts_synth(script, audio) or {}
        if not audio.is_file() or audio.stat().st_size < 1000:
            raise RenderBlocked("TTS output missing or too small")
        narration_duration = float(probe_fn(audio))
        if not 25.0 <= narration_duration <= 48.0:
            raise RenderBlocked(f"Short narration must be 25-48 seconds, got {narration_duration:.2f}")

        captions = _visual_captions(item)
        scenes: list[Path] = []
        for idx, caption in enumerate(captions, 1):
            scene = tmp / f"scene_{idx}.jpg"
            _render_scene(asset, caption, scene, scene_no=idx)
            scenes.append(scene)

        fractions = (0.28, 0.42, 0.30)
        concat = tmp / "scenes.txt"
        lines: list[str] = []
        for scene, fraction in zip(scenes, fractions):
            lines.append(f"file '{scene.as_posix()}'")
            lines.append(f"duration {narration_duration * fraction:.3f}")
        lines.append(f"file '{scenes[-1].as_posix()}'")
        concat.write_text("\n".join(lines) + "\n", encoding="utf-8")

        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
            "-i", str(audio), "-shortest", "-r", "30", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            str(out_path),
        ]
        result = command_runner(cmd, capture_output=True, text=True, timeout=180, check=False)
        if getattr(result, "returncode", 1) != 0:
            raise RenderBlocked(f"ffmpeg failed: {str(getattr(result, 'stderr', ''))[-400:]}")
        if not out_path.is_file() or out_path.stat().st_size < 1000:
            raise RenderBlocked("rendered video missing or too small")
        final_duration = float(probe_fn(out_path))
        if not 25.0 <= final_duration <= 48.0:
            raise RenderBlocked(f"rendered Short must be 25-48 seconds, got {final_duration:.2f}")
        return {
            "path": str(out_path),
            "duration": final_duration,
            "scene_count": len(scenes),
            "output_sha256": _sha256(out_path),
            "tts": tts_meta,
        }


KST = timezone(timedelta(hours=9))


def _receipt_path(bundle_root: Path, date_iso: str, platform: str) -> Path:
    if not re.fullmatch(r"[a-z0-9_]+", platform):
        raise ValueError("invalid platform receipt name")
    return Path(bundle_root) / "receipts" / date_iso / f"{platform}.json"


def _receipt_action(path: Path) -> str:
    path = Path(path)
    if not path.exists():
        return "continue"
    try:
        status = _read_json(path).get("status")
    except Exception:
        return "hold"
    if status == "PUBLISHED":
        return "skip"
    return "hold"


def receipt_state(bundle_root: Path, date_iso: str, platform: str, *, block_if_platform: str | None = None) -> dict:
    primary = _receipt_action(_receipt_path(bundle_root, date_iso, platform))
    if primary != "continue":
        return {"action": primary, "reason": f"{platform}_receipt_{primary}"}
    if block_if_platform:
        blocker = _receipt_action(_receipt_path(bundle_root, date_iso, block_if_platform))
        if blocker == "skip":
            return {"action": "skip", "reason": f"blocked_by_{block_if_platform}"}
        if blocker == "hold":
            return {"action": "hold", "reason": f"unresolved_{block_if_platform}"}
    return {"action": "continue", "reason": "no_receipt"}


def _append_status(path: Path | None, payload: dict) -> None:
    if path is None:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": _now_iso(), **payload}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_existing_readiness(source_root: Path):
    source_root = Path(source_root).resolve()
    project_root = source_root.parent.parent
    module_path = project_root / "publish_2027_series.py"
    if not module_path.is_file():
        raise RuntimeError(f"existing Naver readiness module not found: {module_path}")
    spec = importlib.util.spec_from_file_location("naver_2027_publish_readonly", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load existing Naver readiness module")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "readiness", None)
    if not callable(fn):
        raise RuntimeError("existing Naver readiness() is unavailable")
    return fn


def dispatch_daily(
    *,
    date_iso: str,
    manifest_path: Path,
    source_root: Path,
    send: bool,
    now: datetime | None = None,
    readiness_fn=None,
    command_runner=None,
    lock_path: Path | None = None,
    status_path: Path | None = None,
    repo: str = "gsdo1004-cloud/sajufortune-cards",
    workflow: str = "newyear-2027-fanout.yml",
    mode: str = "normal",
    dispatch_key: str | None = None,
    dispatch_key_path: Path | None = None,
    remote_commit_sha: str | None = None,
) -> dict:
    """Gate locally, then dispatch only the independent 2027 GitHub workflow."""
    command_runner = command_runner or subprocess.run
    now_kst = now or datetime.now(KST)
    if now_kst.tzinfo is None:
        now_kst = now_kst.replace(tzinfo=KST)
    else:
        now_kst = now_kst.astimezone(KST)
    lock_path = Path(lock_path or Path("D:/automation_control/state/newyear_2027_fanout.lock"))

    try:
        with OwnedFileLock(lock_path):
            manifest = load_manifest(Path(manifest_path))
            item = select_manifest_item(manifest, date_iso)
            if item is None:
                result = {"action": "hold", "reason": "no_due_content", "date": date_iso}
                _append_status(status_path, result)
                return result
            readiness_fn = readiness_fn or _load_existing_readiness(Path(source_root))
            gate = source_gate(item, Path(source_root), readiness_fn=readiness_fn)
            if not gate.get("ok"):
                result = {"action": "hold", "reason": gate.get("reason", "source_gate_failed"), "date": date_iso}
                _append_status(status_path, result)
                return result
            if not send:
                result = {"action": "dry_run", "reason": "source_gate_passed", "date": date_iso, "content_id": item["content_id"]}
                _append_status(status_path, result)
                return result
            local_time = now_kst.time().replace(tzinfo=None)
            same_day = now_kst.date().isoformat() == date_iso
            public_window = dt_time(11, 0) <= local_time <= dt_time(14, 0)
            private_canary_window = dt_time(8, 0) <= local_time <= dt_time(19, 0)
            allowed = same_day and (private_canary_window if mode == "youtube_private_canary" else public_window)
            if not allowed:
                result = {"action": "hold", "reason": "outside_safe_dispatch_window", "date": date_iso}
                _append_status(status_path, result)
                return result
            try:
                key = _load_dispatch_key(value=dispatch_key, path=dispatch_key_path)
            except Exception:
                result = {"action": "hold", "reason": "dispatch_key_unavailable", "date": date_iso}
                _append_status(status_path, result)
                return result
            source_url = str(gate.get("naver_url") or "").strip()
            payload_sha256 = publication_payload_sha256(item)
            try:
                commit_sha = str(remote_commit_sha or _resolve_remote_main_sha(repo, command_runner)).strip().lower()
            except Exception:
                result = {"action": "hold", "reason": "remote_commit_unavailable", "date": date_iso}
                _append_status(status_path, result)
                return result
            if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
                result = {"action": "hold", "reason": "remote_commit_invalid", "date": date_iso}
                _append_status(status_path, result)
                return result
            expires_at = (now_kst.astimezone(timezone.utc) + timedelta(minutes=60)).isoformat(timespec="seconds")
            permit = make_dispatch_permit(
                key, item, date_iso, source_url, mode, expires_at, payload_sha256, commit_sha
            )
            cmd = [
                "gh", "workflow", "run", workflow,
                "--repo", repo, "--ref", "main",
                "-f", f"date={date_iso}", "-f", "send=true", "-f", f"mode={mode}",
                "-f", f"source_url={source_url}", "-f", f"expires_at={expires_at}",
                "-f", f"payload_sha256={payload_sha256}", "-f", f"commit_sha={commit_sha}",
                "-f", f"permit={permit}",
            ]
            proc = command_runner(cmd, capture_output=True, text=True, timeout=60, check=False)
            if getattr(proc, "returncode", 1) != 0:
                result = {"action": "hold", "reason": "gh_dispatch_failed", "date": date_iso,
                          "stderr": str(getattr(proc, "stderr", ""))[-500:]}
                _append_status(status_path, result)
                return result
            result = {"action": "dispatched", "reason": "source_gate_passed", "date": date_iso,
                      "content_id": item["content_id"], "workflow": workflow, "mode": mode}
            _append_status(status_path, result)
            return result
    except FileExistsError:
        result = {"action": "hold", "reason": "newyear_2027_lock_busy", "date": date_iso}
        _append_status(status_path, result)
        return result


def _workflow_item(bundle_root: Path, date_iso: str) -> dict:
    manifest = load_manifest(Path(bundle_root) / "content.json")
    item = select_manifest_item(manifest, date_iso)
    if item is None:
        raise RuntimeError(f"no 2027 bundle item for {date_iso}")
    return dict(item)


def _emit_output(path: str | None, **values) -> None:
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as fh:
        for key, value in values.items():
            fh.write(f"{key}={value}\n")


def _cmd_receipt_transition(args) -> int:
    incoming = _read_json(Path(args.incoming))
    durable_path = Path(args.durable)
    current = None
    if durable_path.exists():
        try:
            current = _read_json(durable_path)
        except Exception as exc:
            raise PublicationBlocked("durable receipt is corrupt") from exc
    result = validate_durable_receipt_transition(args.action, current, incoming)
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise PublicationBlocked(f"durable receipt transition blocked: {result.get('reason')}")
    return 0


def _cmd_receipt_owner(args) -> int:
    durable = _read_json(Path(args.durable))
    local = _read_json(Path(args.local))
    result = validate_durable_receipt_owner(durable, local)
    print(json.dumps(result, ensure_ascii=False))
    if not result.get("ok"):
        raise PublicationBlocked(f"durable receipt ownership blocked: {result.get('reason')}")
    return 0


def _cmd_state(args) -> int:
    bundle = Path(args.bundle_root)
    receipt = _receipt_path(bundle, args.date, args.platform)
    state = receipt_state(bundle, args.date, args.platform, block_if_platform=args.block_if_platform)
    print(json.dumps({**state, "receipt": str(receipt)}, ensure_ascii=False))
    _emit_output(args.github_output, action=state["action"], reason=state["reason"], receipt=str(receipt))
    return 0


def _cmd_verify_permit(args) -> int:
    item = _workflow_item(Path(args.bundle_root), args.date)
    key = _load_dispatch_key()
    actual_commit = _current_git_sha()
    expected_commit = str(args.commit_sha or "").strip().lower()
    if actual_commit != expected_commit:
        raise PublicationBlocked(
            f"execution commit mismatch: expected {expected_commit}, got {actual_commit}"
        )
    result = validate_dispatch_authorization(
        key, item, args.date, args.source_url, args.mode, args.expires_at,
        args.payload_sha256, expected_commit, args.permit
    )
    if not result.get("ok"):
        raise PublicationBlocked(f"dispatch permit verification failed: {result.get('reason')}")
    print(json.dumps({
        "ok": True, "content_id": item["content_id"], "date": args.date,
        "mode": args.mode, "payload_sha256": args.payload_sha256, "commit_sha": actual_commit,
    }, ensure_ascii=False))
    return 0


def _cmd_intent(args) -> int:
    bundle = Path(args.bundle_root)
    item = _workflow_item(bundle, args.date)
    receipt = _receipt_path(bundle, args.date, args.platform)
    action = _receipt_action(receipt)
    if action == "continue":
        if args.video:
            video = Path(args.video)
            if not video.is_file():
                raise FileNotFoundError(video)
            item["output_sha256"] = _sha256(video)
        intent_data = prepare_intent(receipt, item=item, platform=args.platform, account=args.account)
        action = "publish"
        owner_token = intent_data["owner_token"]
    else:
        owner_token = ""
    print(json.dumps({"action": action, "receipt": str(receipt), "owner_token": owner_token}, ensure_ascii=False))
    _emit_output(args.github_output, action=action, receipt=str(receipt), owner_token=owner_token)
    return 0


def _cmd_render(args) -> int:
    bundle = Path(args.bundle_root)
    item = _workflow_item(bundle, args.date)
    out = Path(args.output or (bundle / "rendered" / f"{args.date}.mp4"))
    result = render_short(item, bundle, out)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _cmd_publish_threads(args) -> int:
    bundle = Path(args.bundle_root)
    item = _workflow_item(bundle, args.date)
    receipt = _receipt_path(bundle, args.date, "threads")
    mode = os.environ.get("AUTH_MODE", "").strip()
    guard = runtime_authorization_guard(item, args.date, mode)
    print(publish_threads_text(
        item, receipt_path=receipt, account=args.account, authorization_guard=guard
    ))
    return 0


def _cmd_publish_youtube(args) -> int:
    bundle = Path(args.bundle_root)
    item = _workflow_item(bundle, args.date)
    video = Path(args.video or (bundle / "rendered" / f"{args.date}.mp4"))
    item["output_sha256"] = _sha256(video)
    mode = os.environ.get("AUTH_MODE", "").strip()
    guard = runtime_authorization_guard(item, args.date, mode)
    if args.canary:
        if mode != "youtube_private_canary":
            raise PublicationBlocked("private canary requires youtube_private_canary authorization")
        receipt = _receipt_path(bundle, args.date, "youtube_canary")
        remote = publish_youtube_private_canary(
            item, video, receipt_path=receipt, authorization_guard=guard
        )
    else:
        if mode != "normal":
            raise PublicationBlocked("normal YouTube publish requires normal authorization")
        receipt = _receipt_path(bundle, args.date, "youtube")
        remote = publish_youtube(
            item, video, receipt_path=receipt, publish_at=args.publish_at, authorization_guard=guard
        )
    print(remote)
    return 0



def build_bundle(source_root: Path, bundle_root: Path, *, expected_count: int = 60) -> dict:
    """Prebuild the LLM-free 2027 Threads/Shorts manifest and source visuals."""
    from PIL import Image, ImageOps

    source_root = Path(source_root)
    bundle_root = Path(bundle_root)
    posts = [
        p for p in source_root.iterdir()
        if p.is_dir() and re.fullmatch(r"\d{2}_.+", p.name)
    ]
    posts.sort(key=lambda p: int(p.name.split("_", 1)[0]))
    if len(posts) != expected_count:
        raise ValueError(f"expected {expected_count} posts, found {len(posts)}")

    prepared: list[tuple[dict, Path]] = []
    seen_dates: set[str] = set()
    seen_ids: set[str] = set()
    for post_dir in posts:
        entry = build_entry(post_dir)
        date_iso = str(entry.get("publish_date") or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_iso):
            raise ValueError(f"invalid publish_date: {post_dir.name}: {date_iso!r}")
        if date_iso in seen_dates:
            raise ValueError(f"duplicate publish_date: {date_iso}")
        if entry["content_id"] in seen_ids:
            raise ValueError(f"duplicate content_id: {entry['content_id']}")
        hero = post_dir / "images" / "hero.png"
        if not hero.is_file():
            raise FileNotFoundError(f"hero image missing: {hero}")
        if len(entry.get("threads_text", "")) > 500:
            raise ValueError(f"Threads copy exceeds 500 chars: {entry['content_id']}")
        if "2027" not in entry.get("shorts_script", ""):
            raise ValueError(f"Shorts script lost 2027 grounding: {entry['content_id']}")
        seen_dates.add(date_iso)
        seen_ids.add(entry["content_id"])
        prepared.append((entry, hero))

    assets_dir = bundle_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    for entry, hero in prepared:
        target = bundle_root / entry["asset"]
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        with Image.open(hero) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            image.save(tmp, format="JPEG", quality=88, optimize=True, progressive=True)
        os.replace(tmp, target)
        current = dict(entry)
        current["asset_sha256"] = _sha256(target)
        current["asset_bytes"] = target.stat().st_size
        items.append(current)

    manifest = {
        "schema": "newyear_2027/v1",
        "count": len(items),
        "items": items,
    }
    _atomic_json_write(bundle_root / "content.json", manifest)
    return manifest


def _cmd_build_bundle(args) -> int:
    manifest = build_bundle(Path(args.source_root), Path(args.bundle_root), expected_count=args.expected_count)
    print(json.dumps({"schema": manifest["schema"], "count": manifest["count"]}, ensure_ascii=False))
    return 0

def _cmd_dispatch(args) -> int:
    result = dispatch_daily(
        date_iso=args.date,
        manifest_path=Path(args.manifest),
        source_root=Path(args.source_root),
        send=args.send,
        lock_path=Path(args.lock),
        status_path=Path(args.status),
        repo=args.repo,
        workflow=args.workflow,
        mode=args.mode,
        dispatch_key_path=Path(args.dispatch_key_file) if args.dispatch_key_file else None,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["action"] in {"dry_run", "dispatched", "hold"} else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent 2027 Threads/Shorts fanout")
    sub = parser.add_subparsers(dest="command", required=True)

    transition = sub.add_parser("receipt-transition")
    transition.add_argument("--action", required=True, choices=["claim", "finalize"])
    transition.add_argument("--durable", required=True)
    transition.add_argument("--incoming", required=True)
    transition.set_defaults(func=_cmd_receipt_transition)

    owner = sub.add_parser("receipt-owner")
    owner.add_argument("--durable", required=True)
    owner.add_argument("--local", required=True)
    owner.set_defaults(func=_cmd_receipt_owner)

    state = sub.add_parser("state")
    state.add_argument("--date", required=True)
    state.add_argument("--platform", required=True)
    state.add_argument("--bundle-root", default="newyear_2027")
    state.add_argument("--block-if-platform")
    state.add_argument("--github-output")
    state.set_defaults(func=_cmd_state)

    verify = sub.add_parser("verify-permit")
    verify.add_argument("--date", required=True)
    verify.add_argument("--source-url", required=True)
    verify.add_argument("--mode", required=True, choices=["normal", "threads_canary", "youtube_private_canary"])
    verify.add_argument("--expires-at", required=True)
    verify.add_argument("--payload-sha256", required=True)
    verify.add_argument("--commit-sha", required=True)
    verify.add_argument("--permit", required=True)
    verify.add_argument("--bundle-root", default="newyear_2027")
    verify.set_defaults(func=_cmd_verify_permit)

    intent = sub.add_parser("intent")
    intent.add_argument("--date", required=True)
    intent.add_argument("--platform", required=True, choices=["threads", "youtube", "youtube_canary"])
    intent.add_argument("--account", required=True)
    intent.add_argument("--video")
    intent.add_argument("--bundle-root", default="newyear_2027")
    intent.add_argument("--github-output")
    intent.set_defaults(func=_cmd_intent)

    render = sub.add_parser("render")
    render.add_argument("--date", required=True)
    render.add_argument("--bundle-root", default="newyear_2027")
    render.add_argument("--output")
    render.set_defaults(func=_cmd_render)

    threads = sub.add_parser("publish-threads")
    threads.add_argument("--date", required=True)
    threads.add_argument("--bundle-root", default="newyear_2027")
    threads.add_argument("--account", default="gsdo10042026")
    threads.set_defaults(func=_cmd_publish_threads)

    youtube = sub.add_parser("publish-youtube")
    youtube.add_argument("--date", required=True)
    youtube.add_argument("--bundle-root", default="newyear_2027")
    youtube.add_argument("--video")
    youtube.add_argument("--publish-at")
    youtube.add_argument("--canary", action="store_true")
    youtube.set_defaults(func=_cmd_publish_youtube)

    bundle = sub.add_parser("build-bundle")
    bundle.add_argument("--source-root", required=True)
    bundle.add_argument("--bundle-root", default="newyear_2027")
    bundle.add_argument("--expected-count", type=int, default=60)
    bundle.set_defaults(func=_cmd_build_bundle)

    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--date", required=True)
    dispatch.add_argument("--manifest", required=True)
    dispatch.add_argument("--source-root", required=True)
    dispatch.add_argument("--send", action="store_true")
    dispatch.add_argument("--lock", default=r"D:\automation_control\state\newyear_2027_fanout.lock")
    dispatch.add_argument("--status", default=r"D:\automation_control\state\newyear_2027_fanout_status.jsonl")
    dispatch.add_argument("--repo", default="gsdo1004-cloud/sajufortune-cards")
    dispatch.add_argument("--workflow", default="newyear-2027-fanout.yml")
    dispatch.add_argument("--dispatch-key-file")
    dispatch.add_argument("--mode", default="normal", choices=["normal", "threads_canary", "youtube_private_canary"])
    dispatch.set_defaults(func=_cmd_dispatch)

    args = parser.parse_args(argv)
    if args.command == "publish-youtube" and not args.canary and not args.publish_at:
        parser.error("publish-youtube requires --publish-at unless --canary is used")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
