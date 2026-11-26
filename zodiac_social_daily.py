"""Two daily fortune formats; reuse official publishers, never automate replies.
Default is read-only. Every live external effect requires a durable atomic claim.
"""
from __future__ import annotations
import argparse, base64, datetime as dt, hashlib, json, math, os, re, struct, subprocess, tempfile, wave
from pathlib import Path
from zoneinfo import ZoneInfo
import requests
from PIL import Image, ImageDraw, ImageFont

BASE=Path(__file__).resolve().parent
REPO='gsdo1004-cloud/sajufortune-cards'
API=f'https://api.github.com/repos/{REPO}'
RAW=f'https://raw.githubusercontent.com/{REPO}'
KST=ZoneInfo('Asia/Seoul')
SIGNS='쥐띠 소띠 호랑이띠 토끼띠 용띠 뱀띠 말띠 양띠 원숭이띠 닭띠 개띠 돼지띠'.split()
ANIMALS='rat ox tiger rabbit dragon snake horse goat monkey rooster dog pig'.split()
KINDS={'ig_image':('instagram_pub_image_reel.json',10,0),'ig_short':('instagram_pub_reel.json',18,0),'threads_short':('threads_pub_reels.json',18,10)}
SLOTS={'0 1 * * *':'ig_image','20 1 * * *':'ig_image','0 9 * * *':'ig_short','30 9 * * *':'ig_short','10 9 * * *':'threads_short','40 9 * * *':'threads_short'}

def require(ok,msg):
    if not ok: raise RuntimeError(msg)
def sha(b): return hashlib.sha256(b).hexdigest()
def date_check(day): require(dt.date.fromisoformat(day).isoformat()==day,'invalid date')
def time_allowed(kind,day,now):
    _,h,m=KINDS[kind]; start=dt.datetime.combine(dt.date.fromisoformat(day),dt.time(h,m),KST)
    return start<=now<start+dt.timedelta(hours=2)
def marker(kind,day): return f'cards/{day}/{KINDS[kind][0]}'
def claim_path(kind,day): return f'cards/{day}/social_claim_{kind}.json'
def public_get(url,limit=24_000_000):
    with requests.get(url,stream=True,timeout=40) as r:
        r.raise_for_status(); data=bytearray()
        for chunk in r.iter_content(128*1024):
            data.extend(chunk); require(len(data)<=limit,'asset too large')
        return bytes(data)
def raw(commit,path): return f'{RAW}/{commit}/{path}'
class GitHub:
    def __init__(self,token=''):
        self.s=requests.Session(); self.s.headers.update({'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
        if token:self.s.headers['Authorization']='Bearer '+token
    def get(self,path):
        r=self.s.get(API+path,timeout=30)
        if r.status_code==404:return None
        r.raise_for_status();return r.json()
    def head(self):
        v=self.get('/git/ref/heads/main');require(v,'main ref unavailable');return v['object']['sha']
    def existing(self,path):return self.get('/contents/'+path+'?ref=main')
    def put(self,path,content,message,old_sha=None):
        data={'branch':'main','message':message,'content':base64.b64encode(content).decode()}
        if old_sha:data['sha']=old_sha
        r=self.s.put(API+'/contents/'+path,json=data,timeout=60)
        # Never retry ambiguous writes. A claim may already exist remotely.
        require(r.status_code in (200,201),f'GitHub durable write blocked HTTP={r.status_code}')
        return r.json()

def decode_meta(data,day):
    meta=json.loads(data);require(meta.get('date')==day and meta.get('zodiac_signs')==SIGNS,'wrong date/signs')
    # Scope only the already-approved legacy short contract; PR25 FLUX is not enabled here.
    require(meta.get('contract')=='zodiac12-avatar-safe-v2','unapproved short contract')
    require('flux' not in json.dumps(meta,ensure_ascii=False).lower(),'FLUX source requires separate approval')
    d=dt.date.fromisoformat(day);source=' '.join(meta['narration'][:3]);require(f'{d.month}월 {d.day}일' in source,'date text mismatch')
    rows=[]
    for sign in SIGNS:
        hits=re.findall(r'(?<![가-힣])'+re.escape(sign)+r'\s*,\s*([^.!?]+)',source)
        require(len(hits)==1 and 5<=len(hits[0].strip())<=100,'invalid narration '+sign)
        rows.append((sign,hits[0].strip()))
    return meta,rows

def probe(path,kind):
    d=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],timeout=30))
    v=next(x for x in d['streams'] if x['codec_type']=='video');a=next(x for x in d['streams'] if x['codec_type']=='audio');duration=float(d['format']['duration'])
    require((v['width'],v['height'],v['codec_name'],a['codec_name'])==(1080,1920,'h264','aac'),'bad video format')
    require(7.9<=duration<=8.1 if kind=='ig_image' else 1<=duration<=85,'bad duration');return duration

def render_image(day,rows,work):
    d=dt.date.fromisoformat(day); im=Image.new('RGB',(1080,1920),'#f9f3e8'); dr=ImageDraw.Draw(im)
    def font(size,bold=False):return ImageFont.truetype(str(BASE/'assets/fonts'/('NanumGothic-Bold.ttf' if bold else 'NanumGothic-Regular.ttf')),size)
    dr.rounded_rectangle((44,230,1036,1530),radius=44,fill='#fffaf3',outline='#dbc9a5',width=3)
    dr.text((540,290),f'{d.month}월 {d.day}일 {"월화수목금토일"[d.weekday()]}요일',font=font(34,True),fill='#9e532d',anchor='mm')
    dr.text((540,360),'오늘의 12띠 운세',font=font(66,True),fill='#173e3a',anchor='mm')
    dr.text((540,420),'내 띠를 찾아 오늘의 흐름을 확인하세요',font=font(30),fill='#49635d',anchor='mm')
    for i,(sign,s) in enumerate(rows):
        x=65+i%2*475;y=470+i//2*164
        dr.rounded_rectangle((x,y,x+465,y+151),radius=20,fill=('#e7f0e7' if i%2==0 else '#f5e5d5'))
        with Image.open(BASE/'assets/bg'/f'bg_{ANIMALS[i]}.jpg') as src:
            a=src.convert('RGB');aw,ah=a.size;side=min(aw*.78,ah*.5);cx=.67 if ANIMALS[i]=='goat' else .5;cy=.76 if ANIMALS[i]=='rooster' else .73
            tile=a.crop((int(aw*cx-side/2),int(ah*cy-side/2),int(aw*cx+side/2),int(ah*cy+side/2))).resize((126,126),Image.Resampling.LANCZOS)
        mask=Image.new('L',(126,126));ImageDraw.Draw(mask).ellipse((0,0,125,125),fill=255);im.paste(tile,(x+10,y+12),mask)
        dr.text((x+146,y+11),sign,font=font(34,True),fill='#173e3a')
        f=font(25);lines=[];line=''
        for word in s.split():
            nxt=(line+' '+word).strip()
            if line and dr.textlength(nxt,font=f)>300:lines.append(line);line=word
            else:line=nxt
        if line:lines.append(line)
        require(len(lines)<=4 and all(dr.textlength(z,font=f)<=300 for z in lines),'text overflow '+sign)
        for j,z in enumerate(lines):dr.text((x+146,y+53+j*24),z,font=f,fill='#283632')
    dr.text((540,1490),'대박운세TV · 자기성찰을 위한 운세 해설',font=font(26),fill='#49635d',anchor='mm')
    cover=work/'cover.jpg';im.save(cover,quality=94); audio=work/'original.wav'; sr=44100
    with wave.open(str(audio),'wb') as w:
        w.setparams((1,2,sr,sr*8,'NONE','not compressed')); samples=bytearray()
        for i in range(sr*8):
            t=i/sr;fade=min(1,t/.45,(8-t)/.65);s=sum(math.sin(2*math.pi*f*t+p)*a for f,p,a in [(130.81,0,.035),(196,.7,.025),(261.63,1.2,.018),(329.63,.5,.014)])
            for start,f in [(0,523.25),(1.8,659.25),(3.6,587.33),(5.4,783.99)]:
                z=t-start
                if z>=0:s+=.055*min(1,z/.045)*math.exp(-z*2.2)*math.sin(2*math.pi*f*z)
            samples.extend(struct.pack('<h',int(32767*fade*s)))
        w.writeframes(samples)
    out=work/'image_reel.mp4';subprocess.run(['ffmpeg','-v','error','-y','-loop','1','-i',str(cover),'-i',str(audio),'-t','8','-r','25','-c:v','libx264','-preset','veryfast','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',str(out)],check=True,timeout=90)
    probe(out,'ig_image');return out

def caption(kind,day):
    d=dt.date.fromisoformat(day);date=f'{d.month}월 {d.day}일'
    if kind=='ig_image':return f'내 띠를 찾아 저장해 두세요.\n{date} 12띠 운세 한눈에 보기\n오늘의 공통 흐름을 참고하세요. 개인별 운세는 프로필 링크에서 확인하실 수 있습니다.\n#오늘의운세 #띠별운세 #12띠 #사주'
    if kind=='threads_short':return f'오늘 내 띠의 흐름은 어떨까?\n{date} 12띠 운세를 영상으로 들어보세요.\n공통 운세는 참고용이며, 개인별 오늘운세는 프로필 링크에서 확인할 수 있습니다.'
    import zodiac_instagram as ig
    return ig.reel_caption(day)

def verify_account(kind):
    if kind.startswith('ig_'):
        import zodiac_instagram as ig
        require(ig._account_key()=='gsdo10042026' and ig._expected_username()=='gsdo10042026','wrong Instagram scope');ig.preflight()
    else:
        import zodiac_cardnews as tc
        require(os.environ.get('THREADS_EXPECTED_USERNAME')=='gsdo10042026','wrong Threads scope');uid=tc._threads_uid(os.environ['THREADS_ACCESS_TOKEN'])
        configured=os.environ.get('THREADS_USER_ID','').strip()
        require(not configured or str(uid)==configured,'Threads configured user ID mismatch')
    print('ACCOUNT_PREFLIGHT_PASS',kind)

def publish(kind,day,gh,live=False,now=None):
    date_check(day);clock_override=now;now=now or dt.datetime.now(KST); p=marker(kind,day); lock=claim_path(kind,day)
    existing=gh.existing(p) or gh.existing(lock)
    if existing:print('SKIP_EXISTING_RECEIPT_OR_CLAIM',p);return 'SKIP'
    if live:require(time_allowed(kind,day,now),'outside safe slot')
    require(not gh.existing('scripts/zodiac_publish_guard.py'),'signed release guard present: integrate this route before publishing')
    commit=gh.head();meta_data=public_get(raw(commit,f'cards/{day}/shorts_meta.json'),100_000);meta,rows=decode_meta(meta_data,day)
    uploaded=json.loads(public_get(raw(commit,f'cards/{day}/uploaded.json'),100_000));require(uploaded.get('date')==day and uploaded.get('video_id'),'canonical upload marker missing')
    with tempfile.TemporaryDirectory() as td:
        work=Path(td);asset_path=f'reels/{day}_tts.mp4'
        if kind=='ig_image':
            path=render_image(day,rows,work);asset_path=f'reels/{day}_image_reel_v1.mp4';media=path.read_bytes()
        else:
            media=public_get(raw(commit,asset_path));path=work/'short.mp4';path.write_bytes(media);probe(path,kind)
        print('MEDIA_PASS',kind,day,sha(media),len(media))
        if not live:return 'DRY_RUN'
        # Confirm the owner before any effect; existing publishers keep their own checks.
        verify_account(kind)
        if kind.startswith('ig_'):import zodiac_instagram as ig
        if kind=='ig_image':
            # Asset path is deterministic. Never overwrite an earlier derivative.
            asset=gh.existing(asset_path)
            if asset:
                asset_commit=gh.head();require(sha(public_get(raw(asset_commit,asset_path)))==sha(media),'asset already exists with different bytes')
            else:
                asset_commit=gh.put(asset_path,media,f'chore: approved legacy zodiac image derivative {day}')['commit']['sha']
            url=raw(asset_commit,asset_path)
        else:url=raw(commit,asset_path)
        from media_preflight import check_public_media
        ok,why=check_public_media(url,'video');require(ok,'public media not ready: '+why)
        # Persist claim on main before any Meta POST. A second runner or ambiguous
        # response cannot retry publishing. The same old IG/Threads marker is honored.
        claim={'state':'PUBLISHING','date':day,'kind':kind,'account_key':'gsdo10042026','media_url':url,'media_sha256':sha(media),'source_sha256':sha(meta_data),'claimed_at':now.isoformat()}
        if gh.existing(p) or gh.existing(lock):print('SKIP_RACE');return 'SKIP'
        require(time_allowed(kind,day,dt.datetime.now(KST)) if clock_override is None else time_allowed(kind,day,now),'outside safe slot before claim')
        res=gh.put(lock,json.dumps(claim,ensure_ascii=False).encode(),f'chore: claim {kind} {day}')
        claim_sha=res['content']['sha']
        try:
            if kind.startswith('ig_'):pid=ig.publish_reel(url,caption(kind,day))
            else:
                from zodiac_reels import publish_video
                pid=publish_video(url,caption(kind,day))
            require(str(pid).isdigit(),'missing remote post id')
        except BaseException:
            print('HOLD: durable claim exists; reconcile remote status manually; never retry');raise
        receipt={**claim,'state':'PUBLISHED','post_id':str(pid),'published_at':dt.datetime.now(KST).isoformat()}
        if kind=='ig_short': receipt.update(kind='reel',experiment_variant='canonical',profile_campaign='instagram_reels_revenue')
        elif kind=='ig_image': receipt.update(kind='image_reel',profile_campaign='instagram_image_reel')
        gh.put(p,json.dumps(receipt,ensure_ascii=False).encode(),f'chore: receipt {kind} {day}')
        try:gh.put(lock,json.dumps(receipt,ensure_ascii=False).encode(),f'chore: close claim {kind} {day}',claim_sha)
        except Exception:print('WARN: receipt persisted; claim close needs reconciliation')
        print('PUBLISHED',kind,day,pid);return 'PUBLISHED'

def live_authorized(env,kind):
    return (env.get('ZODIAC_TWO_SLOT_LIVE')=='1' and env.get('GITHUB_REF')=='refs/heads/main' and
            (env.get('GITHUB_EVENT_NAME')=='schedule' or
             (env.get('GITHUB_EVENT_NAME')=='workflow_dispatch' and kind in ('ig_image','ig_short') and env.get('ZODIAC_LOCAL_DISPATCH')=='1')))

def main():
    p=argparse.ArgumentParser();p.add_argument('--kind',choices=KINDS,required=True);p.add_argument('--date',required=True);p.add_argument('--live',action='store_true');p.add_argument('--account-check',action='store_true');a=p.parse_args()
    if a.account_check:
        require(not a.live,'account check cannot publish');verify_account(a.kind);return
    if a.live:require(live_authorized(os.environ,a.kind),'live not authorized by scheduled workflow')
    publish(a.kind,a.date,GitHub(os.environ.get('GH_TOKEN','')),a.live)
if __name__=='__main__':main()
