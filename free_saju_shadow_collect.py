# -*- coding: utf-8 -*-
"""Read-only free-saju Shadow collector for Instagram/Threads.

Writes only anonymized evidence. Never publishes, replies, DMs, or stores raw
comment text/usernames/birth data in the artifact.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os
from pathlib import Path

BASE=Path(__file__).resolve().parent
OUT=BASE/"free_saju_shadow_artifact.json"
KEYWORDS=("사주","재물","재물운","직장","직장운","연애","연애운","운세")

def anon(channel: str, source_id: str) -> str:
    salt=os.environ.get("FREE_SAJU_SHADOW_HASH_SALT","local-shadow-v1")
    return hashlib.sha256(f"{salt}|{channel}|{source_id}".encode()).hexdigest()[:24]

def keyword(text: str) -> str|None:
    t=(text or "").replace(" ","")
    return next((k for k in KEYWORDS if k in t),None)

def record(channel: str, source_id: str, text: str, timestamp=None) -> dict:
    # Parser/engine are intentionally false until local Shadow processing proves them.
    return {"schema":1,"channel":channel,"source_id_hash":anon(channel,source_id),
            "qualified":bool(keyword(text)),"parser_success":False,"engine_success":False,
            "duplicate":False,"privacy_reexposure":False,"accepted_tone_violation":False,
            "api_anomaly":False,"complaint_signal":False,"timestamp":timestamp}

def collect_instagram() -> list[dict]:
    import instagram_comments as ig
    _, candidates=ig.discover()
    return [record("instagram",str(x.get("comment_id") or ""),str(x.get("text") or ""),x.get("timestamp"))
            for x in candidates if x.get("comment_id") and keyword(str(x.get("text") or ""))]

def collect_threads() -> list[dict]:
    import threads_growth as th
    tok=os.environ.get("THREADS_ACCESS_TOKEN","").strip()
    uid=os.environ.get("THREADS_USER_ID","").strip()
    if not tok or not uid: raise RuntimeError("THREADS_ACCESS_TOKEN/THREADS_USER_ID missing")
    cfg=th.load_config(); state=th.load_state(); api=th.ThreadsAPI(tok)
    # Read-only: inbound_candidates only GETs own posts/conversations.
    rows=th.inbound_candidates(api,cfg,state)
    return [record("threads",x.id,x.text,x.timestamp) for x in rows if keyword(x.text)]

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--channel",choices=("instagram","threads","all"),default="all")
    a=ap.parse_args(); rows=[]; errors={}
    for ch,fn in (("instagram",collect_instagram),("threads",collect_threads)):
        if a.channel not in ("all",ch): continue
        try: rows.extend(fn())
        except Exception as e: errors[ch]=type(e).__name__+":"+str(e)[:180]
    payload={"schema":1,"generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),
             "mode":"shadow_read_only","records":rows,"errors":errors}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"records":len(rows),"errors":errors},ensure_ascii=False))
    return 0 if not errors else 2

if __name__=="__main__": raise SystemExit(main())
