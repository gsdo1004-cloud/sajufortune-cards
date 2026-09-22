# -*- coding: utf-8 -*-
"""B-line: revenue-optimized original fortune video. Does not touch legacy daily publishing."""
from __future__ import annotations
import argparse, datetime as dt, json, os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from shortform_revenue_strategy import topic_for, caption, validate_reward_video
BASE=Path(__file__).resolve().parent
OUT=BASE/'reels_revenue'; CARDROOT=BASE/'revenue_cards'
FONT=Path(r'C:\Windows\Fonts\malgunbd.ttf')
TOPIC_BODY={
 '오늘 재물운이 강한 띠':['재물운은 한 번의 큰 행운보다 돈의 흐름을 읽는 습관에서 시작합니다.','오늘은 지출을 먼저 정리하고 꼭 필요한 결정에 집중해 보세요.','기회가 보여도 서두르기보다 조건과 숫자를 확인하는 것이 좋습니다.','같은 띠라도 생년월일에 따라 흐름은 달라집니다.'],
 '이번 주 귀인이 들어오는 띠':['귀인은 꼭 낯선 사람이 아니라 이미 알고 지내던 인연일 수 있습니다.','이번 주에는 먼저 안부를 건네고 도움을 주고받을 연결을 살펴보세요.','말 한마디와 약속을 지키는 태도가 새로운 기회를 만드는 시기입니다.','좋은 인연은 기다리기보다 관계를 관리할 때 더 잘 보입니다.'],
 '2027년 재물운이 좋아지는 띠':['2027년 재물운은 띠 하나만으로 확정할 수 없지만 큰 흐름을 보는 출발점은 됩니다.','수입의 변화만큼 현금흐름과 고정지출을 함께 점검하는 것이 중요합니다.','좋은 운은 무리한 투자보다 준비된 선택과 꾸준한 실행에서 활용도가 높아집니다.','개인별 재물 흐름은 생년월일과 사주 구성에 따라 달라집니다.'],
 '말년운이 좋아지는 사주의 특징':['말년운은 나이만으로 정해지기보다 생활 습관과 관계, 재정 관리가 함께 작용합니다.','명리에서는 후반기의 흐름을 시기별 운의 변화와 함께 살펴봅니다.','지금부터 건강한 관계와 지출 구조를 정돈하면 후반기 선택지가 넓어집니다.','운세는 방향을 참고하는 도구로 활용하는 것이 좋습니다.'],
 '직장운이 바뀌는 신호':['직장운의 변화는 이직만 뜻하지 않고 역할과 관계, 일하는 방식의 변화도 포함합니다.','반복해서 새로운 제안이 들어오거나 책임 범위가 바뀐다면 흐름을 점검해 보세요.','감정적으로 결정하기보다 조건과 장기 방향을 적어 비교하는 것이 좋습니다.','개인의 시기는 생년월일에 따라 달라질 수 있습니다.'],
 '연애운이 풀리는 시기':['연애운은 새로운 만남뿐 아니라 기존 관계가 깊어지는 흐름도 포함합니다.','대화가 자연스럽게 이어지는 인연과 약속을 지키는 사람을 눈여겨보세요.','관계를 서두르기보다 서로의 생활 리듬을 확인하는 것이 중요합니다.','개인별 인연의 시기는 생년월일에 따라 다르게 나타납니다.'],
}
def _font(n): return ImageFont.truetype(str(FONT),n) if FONT.exists() else ImageFont.load_default()
def script(date_iso):
 t=topic_for(date_iso); body=TOPIC_BODY[t]
 return [f'{t}. 오늘은 검색해서 들어오신 분들이 가장 궁금해하는 핵심부터 말씀드리겠습니다.',*body,'마지막으로 오늘 할 수 있는 작은 행동 하나를 정해 보세요. 운은 참고하되 중요한 결정은 현실의 정보와 함께 판단하세요.']
def cards(date_iso):
 t=topic_for(date_iso); d=CARDROOT/date_iso; d.mkdir(parents=True,exist_ok=True); lines=script(date_iso)
 for i,text in enumerate(lines,1):
  im=Image.new('RGB',(1080,1920),(246,239,224)); dr=ImageDraw.Draw(im); dr.rounded_rectangle((70,150,1010,1770),radius=45,fill=(255,252,245),outline=(145,105,55),width=4)
  dr.text((110,220),f'{i:02d}  운명과학',font=_font(42),fill=(100,65,35)); dr.text((110,330),t,font=_font(58),fill=(50,35,25))
  words=text.split(); rows=[]; row=''
  for w in words:
   q=(row+' '+w).strip()
   if dr.textlength(q,font=_font(46))>820: rows.append(row); row=w
   else: row=q
  if row: rows.append(row)
  y=610
  for row in rows: dr.text((120,y),row,font=_font(46),fill=(35,35,35)); y+=76
  dr.text((120,1580),'사주·운세는 참고용입니다',font=_font(34),fill=(110,95,80)); im.save(d/f'revenue_{i:02d}.png',optimize=True)
 return d
def build(date_iso):
 os.environ.setdefault('SUPERTONIC_VOICE', os.environ.get('REVENUE_SUPERTONIC_VOICE', 'F3'))
 os.environ.setdefault('SUPERTONIC_OFF', '0')
 d=cards(date_iso); import zodiac_reels as zr
 # isolated card stem via temporary links/copies in existing date dir, then move output to B-line dir
 legacy=BASE/'cards'/date_iso; legacy.mkdir(parents=True,exist_ok=True); made=[]
 import shutil
 for p in sorted(d.glob('revenue_*.png')):
  q=legacy/p.name; shutil.copyfile(p,q); made.append(q)
 try: out=zr.make_reel_tts(date_iso,card_stem='revenue_',narrs=script(date_iso),out_name=f'{date_iso}_revenue.mp4')
 finally:
  for q in made: q.unlink(missing_ok=True)
 OUT.mkdir(exist_ok=True); target=OUT/out.name; shutil.move(str(out),target)
 sec=zr._dur(target); ok,why=validate_reward_video(sec)
 meta={'tts_primary':'Supertonic','tts_voice':os.environ.get('SUPERTONIC_VOICE'),'tts_fallback':'Edge TTS','date':date_iso,'topic':topic_for(date_iso),'duration':sec,'reward_gate':ok,'gate_reason':why,'tiktok_caption':caption(date_iso,'tiktok'),'instagram_caption':caption(date_iso,'instagram'),'video':str(target)}
 (OUT/f'{date_iso}_revenue.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
 if not ok: raise SystemExit(f'[FAIL] {why}')
 print(json.dumps(meta,ensure_ascii=False,indent=2)); return target
if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('--date',default=dt.date.today().isoformat()); ap.add_argument('--meta',action='store_true'); a=ap.parse_args()
 if a.meta: print(json.dumps({'date':a.date,'topic':topic_for(a.date),'script':script(a.date),'caption':caption(a.date)},ensure_ascii=False,indent=2))
 else: build(a.date)
