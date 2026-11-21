# -*- coding: utf-8 -*-
"""Read-only, privacy-safe Instagram and Threads shadow collection."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "free_saju_shadow_artifact.json"
KEYWORDS = ("사주","재물","재물운","직장","직장운","연애","연애운","운세")
IG_SOURCE = None

def anon(channel: str, source_id: str) -> str:
    salt = os.environ.get("FREE_SAJU_SHADOW_HASH_SALT", "local-shadow-v1")
    return hashlib.sha256(f"{salt}|{channel}|{source_id}".encode()).hexdigest()[:24]

def keyword(text: str) -> str | None:
    t = (text or "").replace(" ", "")
    return next((k for k in KEYWORDS if k in t), None)

def record(channel: str, source_id: str, text: str, timestamp=None) -> dict:
    return {"schema":1,"channel":channel,"source_id_hash":anon(channel,source_id),
            "qualified":bool(keyword(text)),"parser_success":False,"engine_success":False,
            "duplicate":False,"privacy_reexposure":False,"accepted_tone_violation":False,
            "api_anomaly":False,"complaint_signal":False,"timestamp":timestamp}

def safe_reason(exc: Exception) -> str:
    """Never persist an exception message, URL, token, text, or account ID."""
    s = str(exc).lower()
    if "code=190" in s or "session has expired" in s or "token has expired" in s:
        return "auth_expired"
    if "code=10" in s or "code=200" in s or "permission" in s:
        return "permission_denied"
    if "missing" in s and ("token" in s or "user_id" in s):
        return "missing_credentials"
    if "identity_mismatch" in s:
        return "identity_mismatch"
    if "timeout" in s or "connection" in s:
        return "network_error"
    return "api_error"

class ChannelError(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)

def collect_instagram() -> list[dict]:
    """Read-only profile verification before any legacy-token fallback."""
    global IG_SOURCE
    IG_SOURCE = None
    import instagram_comments as ig
    expected = str(ig.cfg().get("account_username", "")).casefold()
    candidates = (("primary","INSTAGRAM_ACCESS_TOKEN","INSTAGRAM_USER_ID"),
                  ("legacy","INSTAGRAM_LEGACY_ACCESS_TOKEN","INSTAGRAM_LEGACY_USER_ID"))
    failures = []
    for name,tkey,ikey in candidates:
        token,uid = os.getenv(tkey,"").strip(),os.getenv(ikey,"").strip()
        if not token or not uid:
            failures.append("missing_credentials")
            continue
        try:
            profile = ig.api_get(uid, {"fields":"id,username","access_token":token})
            if str(profile.get("username") or "").casefold() != expected:
                failures.append("identity_mismatch")
                continue
            original = {k:os.environ.get(k) for k in ("INSTAGRAM_ACCESS_TOKEN","INSTAGRAM_USER_ID")}
            try:
                os.environ["INSTAGRAM_ACCESS_TOKEN"] = token
                os.environ["INSTAGRAM_USER_ID"] = uid
                _, found = ig.discover()
            finally:
                for key,value in original.items():
                    if value is None: os.environ.pop(key,None)
                    else: os.environ[key] = value
            IG_SOURCE = name
            return [record("instagram",str(x.get("comment_id") or ""),
                           str(x.get("text") or ""),x.get("timestamp"))
                    for x in found if x.get("comment_id") and keyword(str(x.get("text") or ""))]
        except Exception as exc:
            failures.append(safe_reason(exc))
    raise ChannelError(next((r for r in failures if r != "missing_credentials"),"missing_credentials"))

def collect_threads() -> list[dict]:
    import threads_growth as th
    token,uid = os.getenv("THREADS_ACCESS_TOKEN","").strip(),os.getenv("THREADS_USER_ID","").strip()
    if not token or not uid: raise ChannelError("missing_credentials")
    rows = th.inbound_candidates(th.ThreadsAPI(token),th.load_config(),th.load_state())
    return [record("threads",x.id,x.text,x.timestamp) for x in rows if keyword(x.text)]

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--channel",choices=("instagram","threads","all"),default="all")
    chosen = p.parse_args().channel
    records,channels,errors = [],{},{}
    for name,fn in (("instagram",collect_instagram),("threads",collect_threads)):
        if chosen not in ("all",name): continue
        try:
            result = fn()
            records.extend(result)
            channels[name] = {"status":"ok","records":len(result)}
            if name == "instagram" and IG_SOURCE:
                channels[name]["auth_source"] = IG_SOURCE
        except Exception as exc:
            reason = exc.reason if isinstance(exc,ChannelError) else safe_reason(exc)
            channels[name] = {"status":"error","reason":reason}
            errors[name] = reason
    successful = any(x["status"]=="ok" for x in channels.values())
    status = "HEALTHY" if not errors else ("DEGRADED" if successful else "FAILED")
    artifact = {"schema":1,"generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),
                "mode":"shadow_read_only","status":status,"channels":channels,
                "records":records,"errors":errors}
    OUT.write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":status,"records":len(records),"channels":channels},ensure_ascii=False))
    return 0 if successful else 2

if __name__ == "__main__":
    raise SystemExit(main())
