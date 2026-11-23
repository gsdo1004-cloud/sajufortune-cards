#!/usr/bin/env python3
"""Portable stdlib-only quality guard for the 10 future revised Newyear 2027 items.
This script NEVER sends, uploads, uses credentials, writes a file, or opens a network connection.
"""
from __future__ import annotations
import argparse
from datetime import date,timedelta
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

DATES=[(date(2026,11,24)+timedelta(days=x)).isoformat() for x in range(10)]
ALLOWED={"source_sha256","naver_title","threads_text","shorts_script","youtube_title","summary_points"}
TEN={
 "39_gapmok":("갑목","상관"),"40_eulmok":("을목","식신"),
 "41_byeonghwa":("병화","겁재"),"42_jeonghwa":("정화","비견"),
 "43_muto":("무토","정인"),"44_gito":("기토","편인"),
 "45_gyeonggeum":("경금","정관"),"46_singeum":("신금","편관"),
 "47_imsu":("임수","정재"),"48_gyesu":("계수","편재"),
}

def fail(reason):
    raise ValueError("SAFE_CI_HOLD: "+reason)

def load_json(src:str)->dict:
    def strict(items):
        result={}
        for k,v in items:
            if k in result:fail("duplicate JSON key "+k)
            result[k]=v
        return result
    data=json.loads(src,object_pairs_hook=strict)
    if not isinstance(data,dict):fail("invalid manifest shape")
    return data

def inspect(current:dict,baseline:dict,asset_root:Path)->dict:
    a=current.get("items");b=baseline.get("items")
    if not isinstance(a,list) or not isinstance(b,list) or len(a)!=60 or len(b)!=60:fail("60 items required")
    if current.get("count")!=60 or baseline.get("count")!=60:fail("count mismatch")
    if current.keys()!=baseline.keys():fail("top-level keys altered")
    if any(current[k]!=baseline[k] for k in baseline if k!="items"):fail("unexpected top-level metadata mutation")
    changed=[];hooks=[];seen=set();imagechecked=0
    for prior,item in zip(b,a):
        if prior.get("content_id")!=item.get("content_id") or prior.get("publish_date")!=item.get("publish_date"):
            fail("item identity/date changed")
        if item['content_id'] in seen:fail("duplicate content id")
        seen.add(item['content_id'])
        if item.keys()!=prior.keys():fail("manifest field set changed")
        diff={k for k in prior if prior[k]!=item[k]}
        if item['publish_date'] in DATES:
            if diff!=ALLOWED:fail("unexpected scoped delta "+item['publish_date']+": "+str(diff))
            key=item.get('source_dir')
            if key not in TEN:fail("unexpected source directory")
            name,god=TEN[key]
            if name not in item['naver_title'] or god not in item['naver_title']:fail("ten-god title mismatch")
            for field,minimum,maximum in (("threads_text",205,500),("shorts_script",250,650)):
                value=item.get(field)
                if not isinstance(value,str) or not minimum<=len(value)<=maximum:fail("copy length invalid")
                if "…" in value or "..." in value or "2027년 2027" in value:fail("copy truncation/duplicate year")
                if name not in value or god not in value:fail("copy missing source classification")
                if "정미년" not in value:fail("copy missing year interpretation")
            if not isinstance(item.get('summary_points'),list) or len(item['summary_points'])!=3:fail("summary count")
            if not item['threads_text'].count("\n\n")>=2:fail("threads structure")
            if not 4<=len(item['youtube_title'])<=100:fail("YouTube title length")
            if not re.fullmatch(r'[0-9a-f]{64}',item['source_sha256']):fail("source SHA shape")
            hooks.append(item['shorts_script'][:32]);changed.append(item['publish_date'])
            image=asset_root/item['asset']
            if not image.is_file():fail("missing image "+str(image))
            data=image.read_bytes()
            if hashlib.sha256(data).hexdigest()!=item['asset_sha256'] or len(data)!=item['asset_bytes']:
                fail("image sha/size mismatch: "+item['asset'])
            imagechecked+=1
        elif diff:
            fail("non-target item mutated "+item['publish_date'])
    if changed!=DATES:fail("expected 10 future dates in order")
    if len(set(hooks))!=10:fail("repeated shorts hook")
    return {"ok":True,"changedCount":10,"unchangedCount":50,"assetHashesChecked":imagechecked,
            "uniqueHooks":len(set(hooks)),"noExternalCalls":True,"publishPermitted":False}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--manifest',default='newyear_2027/content.json')
    ap.add_argument('--asset-root',default='newyear_2027')
    ap.add_argument('--base-file')
    ap.add_argument('--base-ref',default='origin/main')
    args=ap.parse_args()
    current=load_json(Path(args.manifest).read_text(encoding='utf8'))
    if args.base_file:
        baseline=load_json(Path(args.base_file).read_text(encoding='utf8'))
    else:
        proc=subprocess.run(['git','show',f'{args.base_ref}:newyear_2027/content.json'],capture_output=True,text=True,check=True,timeout=15)
        baseline=load_json(proc.stdout)
    print(json.dumps(inspect(current,baseline,Path(args.asset_root)),ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except Exception as e:
        print('QA_FAILED',type(e).__name__,str(e)[:350],file=sys.stderr)
        sys.exit(1)
