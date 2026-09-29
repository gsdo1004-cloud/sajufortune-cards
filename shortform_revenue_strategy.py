# -*- coding: utf-8 -*-
"""TikTok/Reels dual-revenue policy helpers.
Keeps publishing compliant: no engagement manipulation, no duplicated third-party media.
"""
from __future__ import annotations
import datetime as dt

SITE='sajufortune.kr'
SEARCH_TOPICS=(
 '오늘 재물운이 강한 띠','이번 주 귀인이 들어오는 띠','2027년 재물운이 좋아지는 띠',
 '말년운이 좋아지는 사주의 특징','직장운이 바뀌는 신호','연애운이 풀리는 시기')

INSTAGRAM_FORTUNE_CTAS=(
 "내 사주로 재물운도 궁금하다면 댓글에 '재물'만 남겨주세요. DM으로 간단히 봐드릴게요 🔮",
 "요즘 직장운이 답답하다면 댓글에 '직장'만 남겨주세요. DM으로 핵심만 봐드릴게요.",
 "지금 내게 가장 강한 운이 궁금하다면 댓글에 '사주'만 남겨주세요. DM으로 간단풀이 보내드릴게요 🔮",
 "연애 흐름이 궁금하다면 댓글에 '연애'만 남겨주세요. DM으로 짧게 봐드릴게요.",
 "올해 전체 흐름이 궁금하다면 댓글에 '운세'만 남겨주세요. DM으로 핵심만 알려드릴게요.",
)

def topic_for(date_iso:str)->str:
    d=dt.date.fromisoformat(date_iso)
    return SEARCH_TOPICS[d.toordinal()%len(SEARCH_TOPICS)]

def instagram_fortune_cta(date_iso:str)->str:
    d=dt.date.fromisoformat(date_iso)
    # 화/목/일만 무료사주 참여 CTA를 노출한다. 매일 반복하지 않는다.
    if d.weekday() not in {1,3,6}:
        return ''
    return INSTAGRAM_FORTUNE_CTAS[d.toordinal()%len(INSTAGRAM_FORTUNE_CTAS)]

def caption(date_iso:str, platform:str='tiktok')->str:
    d=dt.date.fromisoformat(date_iso); wd='월화수목금토일'[d.weekday()]
    topic=topic_for(date_iso)
    # 5일 중 1일만 홈페이지 CTA: 피드가 광고판처럼 보이지 않게 한다.
    cta = (d.toordinal()%5==0)
    lead=f'{d.month}월 {d.day}일 {wd}요일 · {topic} 🔮'
    body='같은 띠라도 생년월일에 따라 흐름은 달라질 수 있습니다.'
    if platform == 'instagram':
        fortune_cta=instagram_fortune_cta(date_iso)
        if fortune_cta:
            body='같은 띠라도 개인 흐름은 달라질 수 있습니다.'
            body += f'\n\n{fortune_cta}'
        elif cta:
            body += f' 내 생년월일 기준 무료 오늘운세는 프로필 첫 링크 {SITE}에서 확인하세요.'
    elif cta:
        body += f' 내 생년월일 기준 무료 오늘운세는 프로필 첫 링크 {SITE}에서 확인하세요.'
    tags='#오늘의운세 #띠별운세 #사주 #재물운 #운세'
    return f'{lead}\n{body}\n{tags}'

def validate_reward_video(seconds:float)->tuple[bool,str]:
    # TikTok Creator Rewards: at least one minute. 65s gives encoding/measurement margin.
    if seconds < 65: return False, f'{seconds:.1f}s: 수익형은 65초 이상 권장'
    if seconds > 180: return False, f'{seconds:.1f}s: 숏폼 운세 운영 상한(180초) 초과'
    return True, f'{seconds:.1f}s: 수익형 길이 PASS'
