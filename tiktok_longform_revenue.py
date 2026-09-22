# -*- coding: utf-8 -*-
"""TikTok-only longform C-line. Never touches YouTube/A-line."""
from __future__ import annotations
import datetime as dt, json
from pathlib import Path
BASE=Path(__file__).resolve().parent
OUT=BASE/'tiktok_longform_revenue'
TOPICS=(
 '2027년 재물 흐름이 달라지는 시기와 준비법',
 '말년운이 좋아지는 사람에게 보이는 변화',
 '직장운이 바뀌기 전에 나타나는 현실 신호',
 '귀인운이 들어올 때 놓치기 쉬운 사람과 기회',
 '연애운이 풀릴 때 관계에서 달라지는 점',
 '돈의 흐름을 점검할 때 함께 봐야 할 생활 습관',
)
def topic_for(date_iso): return TOPICS[dt.date.fromisoformat(date_iso).toordinal()%len(TOPICS)]
def outline(date_iso):
 t=topic_for(date_iso)
 return [
  f'훅: {t}. 결론부터 말하면 운의 변화는 한 번에 오기보다 생활 속 작은 신호로 먼저 나타납니다.',
  '왜 중요한가: 막연한 길흉보다 지금 확인할 수 있는 변화와 선택 기준을 짚습니다.',
  '핵심 1: 반복되는 제안, 관계, 소비와 일의 패턴에서 이전과 달라진 점을 찾습니다.',
  '핵심 2: 좋은 신호와 경계할 신호를 구분하고 실제 행동으로 옮길 기준을 설명합니다.',
  '사례: 같은 상황도 나이와 생활 조건에 따라 선택이 달라질 수 있음을 구체적인 예로 풉니다.',
  '중간 리텐션: 뒤에서 가장 놓치기 쉬운 한 가지 신호와 현실 점검표를 공개합니다.',
  '핵심 3: 사주 관점의 흐름을 현실의 돈, 일, 관계와 연결하되 단정적인 예언은 피합니다.',
  '실행 체크리스트: 오늘 기록할 것, 일주일 관찰할 것, 결정 전에 비교할 것을 정리합니다.',
  '요약: 핵심 세 가지를 다시 짚고 다음 영상과 연결합니다.',
  'CTA: 개인별 흐름이 궁금한 분만 프로필의 무료 운세를 참고하세요. 중요한 결정은 현실 정보와 함께 판단하세요.'
 ]
def plan(date_iso):
 o=outline(date_iso)
 scenes=[]
 for i,x in enumerate(o,1):
  scenes.append({'scene':i,'seconds_target':40 if i not in (1,10) else 25,'visual_change_sec':8,'pngtuber':'female' if i%2 else 'male','narration':x,'visual_prompt':f'한국적 현대 감성, 세로 9:16, {topic_for(date_iso)}, 장면 {i}, 텍스트 없는 상징적 배경 이미지'})
 return {'platform':'tiktok_only','youtube':False,'date':date_iso,'topic':topic_for(date_iso),'target_minutes':'6-8','publish_frequency':'3/week, ~12/month','tts':'Supertonic; Edge TTS fallback','pngtuber':'existing young male/female','scenes':scenes}
def main():
 import argparse
 ap=argparse.ArgumentParser(); ap.add_argument('--date',default=dt.date.today().isoformat()); a=ap.parse_args()
 OUT.mkdir(exist_ok=True); p=OUT/f'{a.date}_plan.json'; p.write_text(json.dumps(plan(a.date),ensure_ascii=False,indent=2),encoding='utf-8'); print(p)
if __name__=='__main__': main()
