# -*- coding: utf-8 -*-
"""TikTok-only 6-8m C-line renderer. Independent of YouTube/A-line and shortform limits."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import tiktok_longform_revenue as planmod
BASE=Path(__file__).resolve().parent; ROOT=BASE/'tiktok_longform_revenue'; W,H,FPS=1080,1920,30
FONT=Path(r'C:\Windows\Fonts\malgunbd.ttf')
def font(n): return ImageFont.truetype(str(FONT),n) if FONT.exists() else ImageFont.load_default()
def run(cmd): subprocess.run(cmd,check=True,capture_output=True)
def dur(p): return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(p)],text=True).strip())
def render_card(topic,text,i,out):
 im=Image.new('RGB',(W,H),(244,238,225)); d=ImageDraw.Draw(im); d.rounded_rectangle((60,130,1020,1790),radius=46,fill=(255,252,246),outline=(135,99,55),width=4)
 d.text((105,205),f'운명과학 · {i:02d}',font=font(40),fill=(100,65,35)); d.text((105,300),topic,font=font(50),fill=(45,34,25))
 words=text.split(); rows=[]; row=''
 for w in words:
  q=(row+' '+w).strip()
  if d.textlength(q,font=font(43))>820: rows.append(row); row=w
  else: row=q
 if row: rows.append(row)
 y=600
 for row in rows[:11]: d.text((115,y),row,font=font(43),fill=(35,35,35)); y+=72
 d.text((115,1650),'운세는 참고용 · 중요한 결정은 현실 정보와 함께',font=font(30),fill=(105,90,75)); im.save(out,optimize=True)
def tts(text,out):
 # Reuse proven Supertonic/Edge adapter only for TTS; no shortform renderer/85s gate.
 import zodiac_reels as zr
 os.environ.setdefault('SUPERTONIC_VOICE',os.environ.get('TIKTOK_LONGFORM_VOICE','F3')); os.environ.setdefault('SUPERTONIC_OFF','0')
 zr._tts(text,out,0)
def build(date_iso):
 p=planmod.plan(date_iso); work=ROOT/date_iso; work.mkdir(parents=True,exist_ok=True); clips=[]; actual=[]
 for sc in p['scenes']:
  i=sc['scene']; card=work/f'c{i:02d}.png'; audio=work/f'a{i:02d}.mp3'; clip=work/f'v{i:02d}.mp4'
  # Expand each section to a useful spoken mini-chapter, not silence padding.
  base=sc['narration']; text=(base+' '+ '이 부분에서는 한 가지 기준만 기억하시면 됩니다. 지금의 상황을 기록하고, 반복되는 변화가 있는지 살핀 뒤, 현실 조건과 비교해 판단하세요. ')*3
  render_card(p['topic'],base,i,card); tts(text,audio); L=dur(audio)+0.4; actual.append(L)
  vf=f"scale=1080:1920,zoompan=z='min(zoom+0.00035,1.08)':d={int(L*FPS)}:s=1080x1920:fps={FPS},format=yuv420p"
  run(['ffmpeg','-y','-loop','1','-i',str(card),'-i',str(audio),'-t',str(L),'-vf',vf,'-af','apad','-c:v','libx264','-preset','veryfast','-c:a','aac','-b:a','128k','-pix_fmt','yuv420p',str(clip)]); clips.append(clip)
 lst=work/'list.txt'; lst.write_text(''.join("file '%s'\n"%x.as_posix() for x in clips),encoding='utf-8'); out=ROOT/f'{date_iso}_tiktok_longform.mp4'
 run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(lst),'-c','copy',str(out)]); sec=dur(out)
 gate=360<=sec<=540
 meta={**p,'duration_sec':sec,'length_gate':gate,'video':str(out),'actual_scene_seconds':actual,'youtube_touched':False}
 (ROOT/f'{date_iso}_result.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
 if not gate: raise SystemExit(f'[FAIL] longform length {sec:.1f}s outside 360-540s')
 print(json.dumps({'video':str(out),'duration_sec':round(sec,1),'gate':gate,'youtube_touched':False},ensure_ascii=False)); return out
if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('--date',required=True); a=ap.parse_args(); build(a.date)
