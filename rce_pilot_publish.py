# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse, base64, json, os, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

GRAPH = "https://graph.threads.net/v1.0"
EXPECTED_USERNAME = "gsdo10042026"
EXPECTED_CONTENT_ID = "RCE-FORTUNE-TH-20261004-A33D9B36"
KST = timezone(timedelta(hours=9))
PUBLIC_KEY = Path(__file__).resolve().parent / "rce_pilot_dispatch_public_key.pem"
OUTPUT = Path("rce_pilot_receipt_output.json")
RECEIPT_DIR = Path("rce_pilot_receipts")


def _canonical(packet: dict[str, Any]) -> bytes:
    return json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode_packet(value: str) -> dict[str, Any]:
    obj = json.loads(base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("packet must be object")
    return obj


def _parse_iso(value: Any) -> datetime:
    dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt


def _verify(packet: dict[str, Any], signature_b64: str, request_id: str, confirm: str) -> None:
    import re
    if confirm != "PUBLISH_RCE_PILOT":
        raise ValueError("explicit publish confirmation required")
    if packet.get("schema") != "rce-pilot-dispatch-v1":
        raise ValueError("schema mismatch")
    if packet.get("request_id") != request_id or not re.fullmatch(r"RCEPILOTREQ-[A-F0-9]{16}", request_id):
        raise ValueError("request id mismatch")
    if not re.fullmatch(r"RCEPILOT-[A-F0-9]{16}", str(packet.get("pilot_id") or "")):
        raise ValueError("invalid pilot id")
    if packet.get("content_id") != EXPECTED_CONTENT_ID:
        raise ValueError("unsupported content id")
    for key in ("pilot_fingerprint", "copy_fingerprint"):
        if not re.fullmatch(r"[a-f0-9]{64}", str(packet.get(key) or "")):
            raise ValueError(f"invalid {key}")
    if not re.fullmatch(r"RCEPILOTAPP-[A-F0-9]{12}", str(packet.get("approval_id") or "")):
        raise ValueError("invalid approval id")
    if packet.get("platform") != "threads" or packet.get("account_key") != "fortune":
        raise ValueError("platform/account mismatch")
    if packet.get("expected_username") != EXPECTED_USERNAME:
        raise ValueError("unexpected username")
    now = datetime.now(KST)
    requested = _parse_iso(packet.get("requested_at")).astimezone(KST)
    expires = _parse_iso(packet.get("approval_expires_at")).astimezone(KST)
    if requested > now + timedelta(minutes=5) or now - requested > timedelta(minutes=10):
        raise ValueError("dispatch request stale")
    if expires <= now or expires - requested > timedelta(minutes=125):
        raise ValueError("approval invalid")
    post = str(packet.get("post_text") or "")
    reply = str(packet.get("first_reply_text") or "")
    dest = str(packet.get("destination_url") or "")
    if not post or len(post) > 500 or not reply or len(reply) > 500:
        raise ValueError("Threads text invalid")
    if not dest.startswith("https://sajufortune.kr/") or dest not in reply:
        raise ValueError("destination mismatch")
    if f"utm_campaign={EXPECTED_CONTENT_ID}" not in dest:
        raise ValueError("attribution campaign missing")
    key = serialization.load_pem_public_key(PUBLIC_KEY.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("public key type invalid")
    sig = base64.urlsafe_b64decode(signature_b64.encode("ascii"))
    key.verify(sig, _canonical(packet))


def _atomic(path: Path, obj: dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _uid(token: str) -> str:
    data = requests.get(
        f"{GRAPH}/me",
        params={"fields":"id,username","access_token":token},
        timeout=15,
    ).json()
    uid = str(data.get("id") or "").strip()
    username = str(data.get("username") or "").strip().lstrip("@").lower()
    if not uid:
        raise RuntimeError("Threads token owner id missing")
    if username != EXPECTED_USERNAME:
        raise RuntimeError(f"Threads account mismatch: expected @{EXPECTED_USERNAME}, got @{username or 'unknown'}")
    return uid


def _publish_text(uid: str, token: str, text: str, reply_to: str | None = None) -> str:
    payload = {"media_type":"TEXT","text":text,"access_token":token}
    if reply_to:
        payload["reply_to_id"] = reply_to
    j = requests.post(f"{GRAPH}/{uid}/threads", data=payload, timeout=30).json()
    cid = str(j.get("id") or "").strip()
    if not cid:
        raise RuntimeError("Threads container creation failed")
    time.sleep(3)
    j = requests.post(
        f"{GRAPH}/{uid}/threads_publish",
        data={"creation_id":cid,"access_token":token},
        timeout=30,
    ).json()
    pid = str(j.get("id") or "").strip()
    if not pid:
        raise RuntimeError("Threads publish failed")
    return pid


def run(packet_b64: str, signature_b64: str, request_id: str, confirm: str) -> dict[str, Any]:
    packet = _decode_packet(packet_b64)
    _verify(packet, signature_b64, request_id, confirm)
    receipt_path = RECEIPT_DIR / f"{packet['pilot_id']}.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        for key in ("request_id","pilot_id","content_id","pilot_fingerprint","copy_fingerprint","approval_id"):
            if str(receipt.get(key) or "") != str(packet.get(key) or ""):
                raise RuntimeError(f"existing receipt conflict:{key}")
        _atomic(OUTPUT, receipt)
        print(f"[SKIP] authoritative receipt already exists: {receipt_path}")
        return receipt

    token = str(os.environ.get("THREADS_ACCESS_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("THREADS_ACCESS_TOKEN missing")
    uid = _uid(token)
    post_id = _publish_text(uid, token, str(packet["post_text"]))
    now = datetime.now(KST).isoformat(timespec="seconds")
    receipt = {
        "schema":"rce-pilot-publication-receipt-v1",
        "request_id":packet["request_id"],
        "pilot_id":packet["pilot_id"],
        "content_id":packet["content_id"],
        "pilot_fingerprint":packet["pilot_fingerprint"],
        "copy_fingerprint":packet["copy_fingerprint"],
        "approval_id":packet["approval_id"],
        "platform":"threads",
        "account_key":"fortune",
        "username":EXPECTED_USERNAME,
        "post_id":post_id,
        "published_at":now,
        "state":"MAIN_PUBLISHED_REPLY_PENDING",
        "github_run_id":os.environ.get("GITHUB_RUN_ID"),
        "github_repository":os.environ.get("GITHUB_REPOSITORY"),
    }
    _atomic(receipt_path, receipt)
    _atomic(OUTPUT, receipt)
    try:
        reply_id = _publish_text(uid, token, str(packet["first_reply_text"]), reply_to=post_id)
        receipt["reply_post_id"] = reply_id
        receipt["state"] = "COMPLETE"
    except Exception as exc:
        receipt["reply_error"] = f"{type(exc).__name__}:{exc}"[:300]
    _atomic(receipt_path, receipt)
    _atomic(OUTPUT, receipt)
    print(f"[OK] RCE pilot published: {post_id}")
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet-b64", required=True)
    ap.add_argument("--signature-b64", required=True)
    ap.add_argument("--request-id", required=True)
    ap.add_argument("--confirm", required=True)
    a = ap.parse_args()
    result = run(a.packet_b64, a.signature_b64, a.request_id, a.confirm)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
