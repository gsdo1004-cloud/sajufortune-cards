# -*- coding: utf-8 -*-
"""Independent 2027 new-year fortune fanout lane.

The module deliberately keeps the source gate/idempotency core independent from
existing today-fortune pipelines.  Remote publishing and scheduling are added by
later layers; the functions in this section are safe to exercise offline.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

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

    checks = (
        (data.get("success") is True, "naver_success_not_true"),
        (data.get("status") == "PUBLISHED", f"naver_status_{data.get('status') or 'missing'}"),
        (data.get("rss_seen") is True, "naver_rss_not_confirmed"),
        (bool(str(data.get("url") or "").strip()), "naver_url_missing"),
        (data.get("category") == EXPECTED_NAVER_CATEGORY, "naver_category_mismatch"),
    )
    for passed, reason in checks:
        if not passed:
            return {"ok": False, "reason": reason, "status": data.get("status", "")}
    return {
        "ok": True,
        "reason": "published_confirmed",
        "url": str(data["url"]).strip(),
        "published_at": data.get("published_at", ""),
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
    return _clip(core or "2027년 신년운세", 46)


def _threads_text(fmt: str, title: str, bullets: list[str]) -> str:
    b1 = _clip(bullets[0] if bullets else "2027년 운은 결과보다 흐름을 먼저 봐야 합니다.", 78)
    b2 = _clip(bullets[1] if len(bullets) > 1 else "원래 사주와 현재 대운을 함께 봐야 판단이 선명해집니다.", 78)
    b3 = _clip(bullets[2] if len(bullets) > 2 else "지금 바꿀 수 있는 한 가지 행동부터 점검하세요.", 72)
    core = _title_core(title)

    templates = {
        "conclusion": (
            f"{core}, 결론부터 보면 ‘{b1}’입니다.\n"
            "그런데 2027년은 결과보다 먼저 확인할 순서가 있습니다.\n\n"
            f"핵심은 {b2}\n{b3}\n\n몇 년생/어떤 상황인지 댓글로 남기고, 연말에 다시 보려면 저장해 두세요."
        ),
        "checklist": (
            f"2027년 {core}, 이것부터 체크하세요.\n"
            "좋다·나쁘다보다 놓치기 쉬운 한 가지가 더 중요합니다.\n\n"
            f"① {b1}\n② {b2}\n③ {b3}\n\n지금 해당되는 항목을 댓글에 적어보고, 체크용으로 저장해 두세요."
        ),
        "myth_break": (
            f"{core}, ‘운만 좋으면 된다’고 보면 놓칩니다.\n"
            "2027년에는 같은 운도 준비 상태에 따라 결과가 달라집니다.\n\n"
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
    b1 = _clip(bullets[0] if bullets else "결과보다 흐름과 준비 상태를 먼저 점검하세요", 72)
    b2 = _clip(bullets[1] if len(bullets) > 1 else "원래 사주와 현재 대운을 함께 봐야 합니다", 72)
    b3 = _clip(bullets[2] if len(bullets) > 2 else "지금 바꿀 수 있는 행동 한 가지부터 정리하세요", 64)
    basis = "2027년 정미년은 같은 기운도 원국과 대운, 일간의 힘에 따라 체감이 달라집니다."
    # Prefer an explicit source sentence when it carries useful 명리 vocabulary.
    plain = _clean_markdown(article)
    candidates = [s.strip() for s in re.split(r"(?<=[.!?다요])\s+", plain)
                  if any(t in s for t in ("정미", "명리", "대운", "재성", "일간", "원국", "오행"))]
    if candidates:
        basis = _clip(candidates[0], 88)

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
        f"{closers[fmt]} 자세한 2027 운세는 저장해 두고 다음 편도 확인해 보세요."
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
