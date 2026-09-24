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
 '직장운이 바뀌는 신호':['직장운의 변화는 이직만 뜻하지 않습니다. 같은 자리에서도 역할과 책임, 사람 관계, 일하는 방식이 달라지는 때가 먼저 찾아올 수 있습니다.','첫 번째 신호는 반복되는 새로운 제안입니다. 평소와 다른 업무를 맡거나 주변에서 새로운 역할을 권한다면 단순한 우연으로 넘기지 말고 조건을 기록해 보세요.','두 번째는 관계의 변화입니다. 함께 일하는 사람이 바뀌거나 조직의 분위기가 달라질 때는 내가 원하는 방향과 현재 환경이 맞는지 점검할 시점이 될 수 있습니다.','세 번째는 마음의 반응입니다. 예전에는 견딜 만했던 일이 유난히 답답하게 느껴진다면 감정적으로 바로 결정하기보다 급여, 성장 가능성, 통근, 생활 균형을 적어 비교해 보세요.','좋은 변화는 무조건 회사를 옮기는 것이 아니라 지금 자리에서 더 나은 조건을 만드는 선택일 수도 있습니다. 제안이 들어오면 바로 답하지 말고 장단점과 1년 뒤 모습을 함께 비교해 보세요.','개인의 시기는 생년월일과 현실 조건에 따라 달라집니다. 운세는 결정을 대신하는 답이 아니라 놓치고 있던 선택지를 점검하는 참고자료로 활용하는 것이 좋습니다.'],
 '연애운이 풀리는 시기':['연애운은 새로운 만남뿐 아니라 기존 관계가 깊어지는 흐름도 포함합니다.','대화가 자연스럽게 이어지는 인연과 약속을 지키는 사람을 눈여겨보세요.','관계를 서두르기보다 서로의 생활 리듬을 확인하는 것이 중요합니다.','개인별 인연의 시기는 생년월일에 따라 다르게 나타납니다.'],
}

# 짧은 주제는 Supertonic +20%에서 40초대로 끝날 수 있으므로,
# 수익형 길이 게이트(65초)에 여유가 생기도록 의미 있는 보강 문장을 자동으로 붙인다.
REWARD_SCRIPT_TARGET_CHARS=520
REWARD_EXTENSION=[
 '이 흐름을 실제 생활에 적용할 때는 지금 내 상황에서 바꿀 수 있는 것과 당장 바꾸기 어려운 것을 나눠 보는 것이 좋습니다.',
 '좋은 신호가 보여도 한 번에 큰 결정을 하기보다 조건과 일정, 비용을 적어 보고 작은 단계부터 확인하면 실수를 줄일 수 있습니다.',
 '오늘 바로 할 일은 하나면 충분합니다. 연락할 사람, 정리할 지출, 확인할 약속처럼 가장 작은 행동 하나를 정해 실행해 보세요.',
 '하루가 끝난 뒤에는 예상과 실제 결과가 어떻게 달랐는지 짧게 기록해 두세요. 이런 기록이 쌓이면 내 흐름을 더 현실적으로 읽는 데 도움이 됩니다.',
]
def _font(n): return ImageFont.truetype(str(FONT),n) if FONT.exists() else ImageFont.load_default()
def script(date_iso):
 t=topic_for(date_iso); body=TOPIC_BODY[t]
 intro=f'{t}. 오늘은 검색해서 들어오신 분들이 가장 궁금해하는 핵심부터 말씀드리겠습니다.'
 closing='마지막으로 오늘 할 수 있는 작은 행동 하나를 정해 보세요. 운은 참고하되 중요한 결정은 현실의 정보와 함께 판단하세요.'
 lines=[intro,*body]
 for extra in REWARD_EXTENSION:
  if sum(len(x) for x in [*lines,closing]) >= REWARD_SCRIPT_TARGET_CHARS: break
  lines.append(extra)
 return [*lines,closing]
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
