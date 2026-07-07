# sajufortune-cards

**띠별운세 카드뉴스 자동생성 + 스레드 발행** — [sajufortune.kr](https://sajufortune.kr)

매일 KST 새벽, GitHub Actions가 12지(띠별) 오늘의 운세 카드뉴스 8장을 자동 생성해 **스레드(Threads)에 캐러셀로 발행**합니다. 이 repo는 코드 실행과 **카드 이미지 public 호스팅**을 겸합니다.

## 구조
| 파일 | 역할 |
|---|---|
| `zodiac_seo.py` | 12띠 결정론적 운세 데이터 (sajufortune.kr `/zodiac`와 100% 동일, 외부 API·비용 0) |
| `zodiac_cardnews.py` | 카드 생성(HTML→Playwright→PNG) + 스레드 캐러셀 발행 |
| `.github/workflows/zodiac-cards.yml` | 새벽 cron 자동화 |
| `cards/{날짜}/card_01~08.png` | Actions가 생성·커밋 (raw URL로 스레드 발행) |

## 발행 흐름
```
KST 새벽 → 12띠 실데이터 → HTML(흰바탕·핑크테두리·형광펜·띠이모지)
 → Playwright + Noto 이모지로 PNG 8장 → cards/ 커밋(public raw)
 → Threads 캐러셀 발행 → 첫 댓글 "sajufortune.kr/zodiac"
```

## 카드 구성 (8장)
1. 표지 (12지 + 날짜)  ·  2~7. 2띠씩 (별점 + 총운)  ·  8. TOP3 요약 + CTA

## 필요 시크릿 (Settings → Secrets → Actions)
- `THREADS_ACCESS_TOKEN`, `THREADS_USER_ID`

## 수동 실행
Actions 탭 → "띠별운세 카드뉴스" → Run workflow

## 로컬 테스트
```bash
python zodiac_cardnews.py generate   # cards/{날짜}/ 에 PNG 8장
python zodiac_cardnews.py publish     # (커밋 후) 스레드 발행
```
