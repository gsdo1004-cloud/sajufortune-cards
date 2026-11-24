"""Threads-only read/prepare gate. Canonical cards are never modified.
Reviewed PNGs are exact byte allowlists; other dates use the approved static
background renderer in a separate folder, never the FLUX source selector.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, re, shutil, sys, tempfile
from pathlib import Path
from PIL import Image, ImageStat
import requests
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
REVIEW='config/threads_legacy_png_review.json'
SCHEMA='threads-static-carousel-v1'
RAW='https://raw.githubusercontent.com/gsdo1004-cloud/sajufortune-cards'
def need(ok,msg):
    if not ok:raise ValueError(msg)
def day_check(day):need(dt.date.fromisoformat(day).isoformat()==day,'invalid date')
def digest(data):return hashlib.sha256(data).hexdigest()
def file_hash(p):return digest(p.read_bytes())
def hold_new_gate(root):need(not (root/'scripts/zodiac_publish_guard.py').exists(),'signed PR25 release guard present; integrate before using this route')
def review(day,root):
    p=root/REVIEW
    return json.loads(p.read_text(encoding='utf-8')).get(day) if p.exists() else None
def safe_image(p,fmt):
    need(p.is_file() and not p.is_symlink() and 60000<=p.stat().st_size<=8*1024*1024,'invalid card size or path: '+p.name)
    with Image.open(p) as im:im.verify()
    with Image.open(p) as im:
        need(im.format==fmt and im.size==(1080,1920),'invalid card format/dimensions: '+p.name)
        need(max(ImageStat.Stat(im.convert('RGB').resize((128,128))).stddev)>10,'blank card: '+p.name)
def expected_names(mode):return [f'card_{i:02d}.'+('png' if mode=='reviewed_png' else 'jpg') for i in range(1,5 if mode=='reviewed_png' else 7)]
def validate_review(day,root,entry):
    need(entry.get('date')==day and entry.get('review')=='visual_12_signs_complete' and entry.get('source')=='legacy_canonical_png','invalid review identity')
    names=expected_names('reviewed_png');need(list(entry.get('sha256',{}))==names,'incomplete review')
    folder=root/'cards'/day;need(not (folder/'flux_backgrounds_applied.json').exists(),'FLUX-applied source not eligible');need(not (root/'assets/flux_daily'/day).exists(),'FLUX source exists; reviewed PNG route held')
    actual=sorted(p.name for p in folder.glob('card_*.png'));need(actual in (names,names+['card_05.png']) and not list(folder.glob('card_*.jpg')),'mixed or changed reviewed inventory')
    for name in names:
        p=folder/name;safe_image(p,'PNG');need(file_hash(p)==entry['sha256'][name],'review hash mismatch: '+name)
    return [folder/n for n in names]
def verify(day,root=ROOT):
    day_check(day);hold_new_gate(root);folder=root/'threads_cards'/day
    need(folder.is_dir() and not folder.is_symlink(),'missing isolated Threads folder');m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    need(m.get('schema')==SCHEMA and m.get('date')==day and m.get('mode') in ('reviewed_png','static_jpeg'),'invalid manifest')
    mode=m['mode'];names=expected_names(mode);need(list(m.get('sha256',{}))==names,'invalid manifest inventory');need(set(p.name for p in folder.iterdir())==set(names)|{'manifest.json'},'unexpected file in isolated folder')
    if mode=='reviewed_png':
        entry=review(day,root);need(entry is not None and entry['sha256']==m['sha256'],'missing or changed reviewed approval')
        # Exact reviewed copies stay immutable; canonical inputs may later grow.
        need(entry.get('date')==day and entry.get('review')=='visual_12_signs_complete','review date/status mismatch')
    else:
        need(m.get('source')=='existing_approved_static_backgrounds' and m.get('generative_calls')==0,'unapproved static source')
    need(len(set(m['sha256'].values()))==len(names),'duplicate card content')
    for name in names:
        p=folder/name;safe_image(p,'PNG' if mode=='reviewed_png' else 'JPEG');need(file_hash(p)==m['sha256'][name],'asset hash mismatch: '+name)
    print('[PASS]',day,mode,len(names),'isolated Threads cards verified');return [folder/n for n in names]
def prepare(day,root=ROOT):
    day_check(day);hold_new_gate(root);target=root/'threads_cards'/day
    if target.exists():return verify(day,root)
    canonical=root/'cards'/day
    need(not (canonical/'threads_pub_carousel.json').exists(),'already published; no new assets')
    entry=review(day,root);target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.threads-stage-',dir=target.parent) as td:
        work=Path(td)/day;work.mkdir()
        if entry is not None:
            for p in validate_review(day,root,entry):shutil.copyfile(p,work/p.name)
            mode='reviewed_png';source='legacy_canonical_png'
        else:
            # Explicitly independent old photo bank; unknown/mixed canonical assets are never copied or overwritten.
            from zodiac_cardnews_tpl import build
            build(day,output_dir=work,legacy_only=True)
            (work/'visual_style.json').unlink(missing_ok=True)
            mode='static_jpeg';source='existing_approved_static_backgrounds'
        names=expected_names(mode);need(set(p.name for p in work.iterdir())==set(names),'incomplete renderer output')
        for name in names:safe_image(work/name,'PNG' if mode=='reviewed_png' else 'JPEG')
        m={'schema':SCHEMA,'date':day,'mode':mode,'source':source,'generative_calls':0,'sha256':{n:file_hash(work/n) for n in names}}
        (work/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');work.rename(target)
    return verify(day,root)
def public_urls(day,commit,root=ROOT):
    need(bool(re.fullmatch('[0-9a-f]{40}',commit)),'immutable asset commit required')
    paths=verify(day,root);urls=[]
    for p in paths:
        url=f'{RAW}/{commit}/threads_cards/{day}/{p.name}'
        with requests.get(url,stream=True,timeout=30) as r:
            r.raise_for_status();data=bytearray()
            for chunk in r.iter_content(128*1024):
                data.extend(chunk);need(len(data)<=8*1024*1024,'remote asset exceeds limit')
        need(digest(data)==file_hash(p),'remote bytes differ: '+p.name);urls.append(url)
    print('[PASS]',day,'public immutable asset bytes match',len(urls));return urls
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['prepare','verify','public']);a.add_argument('date');a.add_argument('--commit',default='');x=a.parse_args()
    if x.mode=='prepare':prepare(x.date)
    elif x.mode=='verify':verify(x.date)
    else:public_urls(x.date,x.commit)
