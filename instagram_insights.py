# -*- coding: utf-8 -*-
"""Instagram 최근 콘텐츠 성과를 익명 집계 JSON으로 저장한다."""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import requests

BASE=Path(__file__).resolve().parent
API_VERSION=os.environ.get("INSTAGRAM_API_VERSION","v21.0").strip() or "v21.0"
IG=f"https://graph.instagram.com/{API_VERSION}"
OUT=BASE/"analytics"/"instagram_insights.json"


def env():
    uid=os.environ.get("INSTAGRAM_USER_ID","").strip(); tok=os.environ.get("INSTAGRAM_ACCESS_TOKEN","").strip()
    if not uid or not tok: raise RuntimeError("Instagram credentials missing")
    return uid,tok


def collect(limit=30):
    uid,tok=env()
    fields="id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count"
    r=requests.get(f"{IG}/{uid}/media",params={"fields":fields,"limit":limit,"access_token":tok},timeout=30)
    data=r.json()
    if r.status_code>=400: raise RuntimeError(str(data.get("error",{}).get("message") or r.status_code))
    out=[]
    metric_names=("views","reach","saved","shares","total_interactions")
    for item in data.get("data",[]):
        row={k:item.get(k) for k in ("id","media_type","media_product_type","timestamp","permalink","like_count","comments_count")}
        cap=(item.get("caption") or "").replace("\n"," ")
        row["caption_head"]=cap[:120]
        metrics={}
        try:
            q=requests.get(f"{IG}/{item['id']}/insights",params={"metric":",".join(metric_names),"access_token":tok},timeout=30)
            j=q.json()
            if q.status_code<400:
                for m in j.get("data",[]):
                    values = m.get("values") or []
                    value = values[-1].get("value") if values else None
                    if value is None:
                        value = (m.get("total_value") or {}).get("value")
                    if m.get("name") and value is not None:
                        metrics[m.get("name")] = value
        except Exception:
            pass
        row["metrics"]=metrics
        out.append(row)
    return {"collected_at":dt.datetime.now().isoformat(timespec="seconds"),"count":len(out),"media":out}


def main():
    payload=collect()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"[OK] Instagram insights: {payload['count']} media -> {OUT}")

if __name__=="__main__": main()
