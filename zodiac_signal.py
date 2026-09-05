"""띠 지목 게시물(Signal post) 자동 발행 — 매일 낮 한 편.

AI 뉴스가 나가던 낮 자리를 대신한다(2026-08-05 교체). 아침 유령글은 '오늘 일진',
저녁 카드뉴스는 '12띠 전체'라 낮에는 **띠 하나를 생년까지 콕 집어 지목**하는 글을 낸다.
세 편이 서로 겹치지 않는다.

왜 이 형식인가 — 2026-08-05 경쟁 계정 실측(사주장인 54.6K, 팔자읽어주는사람 24.8K)에서
가장 반응이 좋았던 포맷이다. 띠만 쓰면 12분의 1이지만 생년까지 박으면 읽는 사람이
"내 얘긴데?" 하고 멈춘다. 그 멈춤이 체류시간이 되고 체류시간이 도달이 된다.
리서치 정본: `G:\\내 드라이브\\01클로드\\사령부\\2026-08-05_쓰레드사주_경쟁사실측_집PC인계.md`

홍보글이 아니다. 매일 홍보를 밀면 스팸으로 잡힌다(promo_content.py 참고 — 직접 홍보는
토요일 주 1회로만 돈다). 여기서는 콘텐츠를 먼저 주고 프로필로만 유도한다.

본문 규칙(기존 라인과 동일):
  · 링크 URL 금지 — 스레드는 본문 링크가 있으면 도달이 눌린다
  · 반말 (2026-07-27 전환). 스레드에 존댓말 글은 광고로 읽힌다
  · 과장·단정 금지: 무조건·100%·반드시·보장·절대 (PG 심사 규칙)
  · 배타적 연령 표현 금지 — 대박운세는 20~70대 전 연령 대상이다

실행:
  python zodiac_signal.py                # 오늘자 발행
  python zodiac_signal.py --dry-run      # 문구만 출력(발행 안 함)
  python zodiac_signal.py 2026-08-06     # 날짜 지정
  python zodiac_signal.py --sign snake   # 띠 지정(기본은 날짜로 회전)
환경변수: THREADS_ACCESS_TOKEN, THREADS_USER_ID
"""
from __future__ import annotations
import os
import sys
import json
import time
import datetime as dt
from pathlib import Path

import zodiac_seo as zs
import threads_viral_learning as viral
from ganzhi_zodiac import day_context, zodiac_day

BASE = Path(__file__).resolve().parent
GRAPH = "https://graph.threads.net/v1.0"

ORDER = ["rat", "ox", "tiger", "rabbit", "dragon", "snake",
         "horse", "goat", "monkey", "rooster", "dog", "pig"]

# 노출할 생년 범위 — 지금 활동하는 나이대만 뽑는다. 1924년생을 지목해봐야 읽을 사람이 없고,
# 2020년생은 본인이 스레드를 안 한다. 대박운세는 20~70대 전 연령이 대상이라 그 폭으로 잡는다.
# 2026-08-05: 생년을 3개 → 5개로 늘리라는 지시. 띠는 12년 주기라 5개를 담으려면
# 최소 48년 폭이 필요하다. 폭을 위로 늘리면(2008~2012) 만 14세까지 들어가는데 그쪽은
# 운세를 보지도, 결제하지도 않는다 → **아래로** 내려 1948(만 78세)까지 잡는다.
# 이러면 12띠 전부 정확히 5개가 나온다.
BIRTH_MIN, BIRTH_MAX = 1948, 2007
YEARS_SHOWN = 5

# ── 띠별 성향 (명리 12지지 통설) ─────────────────────────────
# 앵글 5개로 나눠 쓴다. 같은 띠라도 날짜에 따라 다른 각도로 나가야 60일간 안 겹친다.
# 문장은 단정하지 않는다 — "~인 편이야", "~할 때가 있어" 로 여지를 둔다.
TRAITS: dict[str, dict[str, tuple[str, str, str]]] = {
    # slug: {angle: (성향 2줄, 내적 갈등 인용, 전환 한 줄)}
    "rat": {
        "money":  ("쥐띠는 돈이 들어오면 먼저 남길 생각부터 하는 편이야.\n쓸 때도 계산이 서 있어야 마음이 놓여.",
                   "\"조금만 더 모으고 나서\"", "모으는 건 이미 충분히 했어. 이제 굴릴 때야."),
        "work":   ("쥐띠는 일이 꼬여도 감정보다 해결책을 먼저 찾아.\n티는 안 내는데 속으로 이미 여러 경우를 계산해 둬.",
                   "\"어떻게든 되겠지\"", "혼자 다 감당할 필요는 없어. 말해도 되는 일이야."),
        "people": ("쥐띠는 사람을 빨리 파악하는 편이야.\n그래서 곁을 잘 안 주고, 준 사람한테는 오래 가.",
                   "\"굳이 말해야 아나\"", "말 안 해도 아는 사이는 생각보다 드물어."),
        "timing": ("쥐띠는 눈치가 빨라서 흐름을 먼저 읽어.\n읽고도 확신이 안 서면 한 박자 미루는 버릇이 있어.",
                   "\"조금만 더 보고\"", "이미 봤잖아. 지금이 그 타이밍이야."),
        "mind":   ("쥐띠는 겉으론 멀쩡한데 머릿속이 늘 바빠.\n쉬는 날에도 뭔가 정리하고 있어.",
                   "\"쉬는 게 더 불안해\"", "가만있는 것도 연습이 필요한 일이야."),
    },
    "ox": {
        "money":  ("소띠는 한 번 정한 방식을 오래 끌고 가.\n느려 보여도 결국 남는 쪽은 이쪽이야.",
                   "\"이 속도로 언제 되나\"", "쌓이는 게 안 보일 뿐이지 안 쌓이는 건 아니야."),
        "work":   ("소띠는 맡은 건 끝까지 해내는 편이야.\n대신 억울해도 잘 말을 안 해.",
                   "\"내가 참으면 되지\"", "참는 게 습관이 되면 알아주는 사람이 없어져."),
        "people": ("소띠는 한번 믿으면 웬만해선 안 흔들려.\n그래서 한 번 크게 데이면 오래 못 잊어.",
                   "\"그래도 사람인데\"", "믿는 건 좋은데 기준은 있어야 해."),
        "timing": ("소띠는 준비가 다 될 때까지 안 움직여.\n그 신중함이 손해로 돌아온 적도 있을 거야.",
                   "\"아직 부족한데\"", "완벽해서 시작하는 사람은 없어."),
        "mind":   ("소띠는 힘들어도 표정이 잘 안 변해.\n그래서 주변에서 괜찮은 줄 알아.",
                   "\"괜찮다고 했잖아\"", "안 괜찮으면 안 괜찮다고 해도 돼."),
    },
    "tiger": {
        "money":  ("범띠는 벌 때 크게 버는 대신 흐름을 타.\n안정적으로 조금씩은 성에 안 차는 편이야.",
                   "\"이 정도로는 안 되지\"", "크게 벌려면 안 잃는 구간도 있어야 해."),
        "work":   ("범띠는 시작하는 힘이 세.\n대신 중간에 흥이 식으면 급격히 느려져.",
                   "\"처음엔 좋았는데\"", "식은 게 아니라 방식이 안 맞은 거야."),
        "people": ("범띠는 앞에 나서는 자리가 익숙해.\n그러다 보니 혼자 짊어지는 것도 익숙해졌어.",
                   "\"내가 안 하면 누가 해\"", "맡기는 것도 능력이야."),
        "timing": ("범띠는 재는 시간이 짧아. 판단이 서면 바로 움직여.\n덕분에 기회를 잡기도, 놓치기도 해.",
                   "\"일단 해보고\"", "이번엔 한 번만 더 확인하고 가."),
        "mind":   ("범띠는 지는 걸 잘 못 견뎌.\n그래서 남들보다 자기를 더 몰아붙여.",
                   "\"아직 멀었어\"", "여기까지 온 것도 쉬운 일이 아니었어."),
    },
    "rabbit": {
        "money":  ("토끼띠는 크게 지르기보다 안전한 쪽을 골라.\n덕분에 크게 잃은 적도 별로 없을 거야.",
                   "\"괜히 건드렸다 잘못되면\"", "안 잃는 것만으론 안 늘어나."),
        "work":   ("토끼띠는 분위기를 먼저 살펴.\n그래서 눈치는 빠른데 정작 자기 의견을 늦게 꺼내.",
                   "\"괜히 말했다가\"", "먼저 말한 사람이 손해 보는 자리면 그 자리가 문제야."),
        "people": ("토끼띠는 부딪히는 걸 싫어해서 웬만하면 맞춰줘.\n맞춰주다 보니 서운한 게 안에 쌓여.",
                   "\"이 정도는 참지\"", "참은 걸 알아주는 사람은 없어. 말해야 알아."),
        "timing": ("토끼띠는 확실해지기 전엔 안 나서.\n그 사이 남이 먼저 가는 걸 여러 번 봤을 거야.",
                   "\"내 차례가 오겠지\"", "차례는 오는 게 아니라 서는 거야."),
        "mind":   ("토끼띠는 상처를 겉으로 잘 안 드러내.\n대신 혼자 오래 곱씹어.",
                   "\"그 말이 계속 걸려\"", "곱씹는다고 그 말이 바뀌진 않아."),
    },
    "dragon": {
        "money":  ("용띠는 판을 크게 보는 편이야.\n작게 시작하는 걸 답답해해서 초반에 무리할 때가 있어.",
                   "\"이왕 할 거면 크게\"", "크게 가려면 버틸 체력부터 있어야 해."),
        "work":   ("용띠는 남이 정해준 길보다 자기가 고른 길에서 힘이 나.\n그래서 시키는 대로만 하는 자리는 오래 못 버텨.",
                   "\"이건 내 일이 아닌 것 같은데\"", "그 느낌이 계속되면 자리를 바꿀 때가 된 거야."),
        "people": ("용띠는 자존심이 세서 아쉬운 소리를 잘 못 해.\n필요할 때도 혼자 해결하려고 들어.",
                   "\"내가 부탁까지 해야 하나\"", "부탁은 지는 게 아니야."),
        "timing": ("용띠는 기대가 커서 시작이 늦어질 때가 있어.\n조건이 다 갖춰지길 기다리는 거야.",
                   "\"아직 때가 아닌데\"", "때를 기다리는 것과 미루는 건 달라."),
        "mind":   ("용띠는 남한테 약한 모습 보이는 걸 싫어해.\n그래서 힘들 때 더 괜찮은 척해.",
                   "\"나는 원래 이래\"", "센 척은 오래 못 가. 티 내도 돼."),
    },
    "snake": {
        "money":  ("뱀띠는 돈 문제에서 감보다 계산을 믿어.\n확신이 안 서면 아예 안 움직여.",
                   "\"조금만 더 지켜볼까\"", "계산은 이미 끝났어. 지금이 움직일 때야."),
        "work":   ("뱀띠는 속내를 잘 안 보여줘.\n다 준비해놓고 마지막에 꺼내는 편이야.",
                   "\"아직 말할 단계는 아니지\"", "혼자 완성하려다 시기를 놓칠 수 있어."),
        "people": ("뱀띠는 사람을 오래 두고 봐.\n한번 선을 그으면 다시 넘어오게 하진 않아.",
                   "\"굳이 다시\"", "선을 긋는 데 쓴 에너지도 만만치 않았을 거야."),
        "timing": ("뱀띠는 머리로 다 계산해놓고 마음이 늘 불안한 편이야.\n완벽한 타이밍만 기다리다 기회를 놓칠 때가 있어.",
                   "\"이게 맞나\"", "맞는지는 해봐야 알아."),
        "mind":   ("뱀띠는 생각이 깊어서 혼자 있는 시간이 필요해.\n그 시간이 없으면 사람한테 날이 서.",
                   "\"좀 혼자 있고 싶은데\"", "혼자 있는 시간은 이기적인 게 아니야."),
    },
    "horse": {
        "money":  ("말띠는 들어오는 만큼 나가는 흐름이 잦아.\n버는 힘은 있는데 묶어두는 힘이 약한 편이야.",
                   "\"또 벌면 되지\"", "버는 힘에 남기는 습관만 붙으면 달라져."),
        "work":   ("말띠는 한자리에 오래 있으면 답답해해.\n움직이는 일에서 성과가 잘 나.",
                   "\"여기 계속 있어야 하나\"", "답답한 건 게으른 게 아니라 안 맞는 거야."),
        "people": ("말띠는 사람 사귀는 데 벽이 낮아.\n대신 깊어지기 전에 다음으로 넘어갈 때가 있어.",
                   "\"다 좋은데 뭔가 허해\"", "넓은 것보다 오래 가는 하나가 필요할 때야."),
        "timing": ("말띠는 결정이 빨라. 재는 시간이 짧아서 남보다 먼저 움직여.\n대신 뒤늦게 후회하는 것도 빨라.",
                   "\"그냥 질러버릴까\"", "이번 건은 하루만 재워두고 봐."),
        "mind":   ("말띠는 가만있는 걸 못 견뎌.\n쉬어도 뭔가 하고 있어야 마음이 편해.",
                   "\"쉬는 것도 지겨워\"", "지겨운 게 아니라 아직 안 쉬어본 거야."),
    },
    "goat": {
        "money":  ("양띠는 사람한테 쓰는 돈을 아깝다고 안 해.\n그러다 정작 자기한테는 인색해져.",
                   "\"나는 나중에\"", "나중이 계속 미뤄지면 그냥 안 하는 거야."),
        "work":   ("양띠는 분위기를 살리는 자리에 잘 어울려.\n대신 평가받는 자리에선 유독 위축돼.",
                   "\"내가 잘하고 있는 건가\"", "잘하고 있어. 확인이 필요했을 뿐이야."),
        "people": ("양띠는 정이 많아서 관계를 잘 못 끊어.\n끊고 나서도 오래 마음이 쓰여.",
                   "\"그래도 한때는 좋았는데\"", "정리한 관계를 계속 되짚으면 새 사람이 못 들어와."),
        "timing": ("양띠는 남의 사정을 먼저 보느라 자기 타이밍을 놓쳐.\n미루다 보면 어느새 지나가 있어.",
                   "\"지금은 좀 그렇지\"", "남 사정 다 맞추면 내 차례는 안 와."),
        "mind":   ("양띠는 인정받고 싶은 마음이 커.\n그래서 작은 말 한마디에 오래 흔들려.",
                   "\"그 사람이 왜 그랬을까\"", "그 말은 그 사람 사정이지 네 값이 아니야."),
    },
    "monkey": {
        "money":  ("원숭이띠는 돈 되는 길을 빨리 찾아내.\n대신 한 우물을 오래 파는 걸 답답해해.",
                   "\"이것도 해볼까\"", "벌리는 것보다 하나를 끝까지 가는 게 남아."),
        "work":   ("원숭이띠는 임기응변이 좋아서 급한 불을 잘 꺼.\n그러다 보니 늘 급한 일만 하고 있어.",
                   "\"이것만 처리하고\"", "급한 일 뒤에 중요한 일이 계속 밀리고 있어."),
        "people": ("원숭이띠는 사람을 편하게 만드는 재주가 있어.\n대신 정작 자기 얘기는 잘 안 해.",
                   "\"내 얘기까지 할 필요는\"", "듣기만 하는 관계는 오래 못 버텨."),
        "timing": ("원숭이띠는 기회를 잘 알아봐.\n동시에 여러 개가 보여서 하나를 못 고를 때가 있어.",
                   "\"이것도 저것도 되는데\"", "다 잡으려다 다 놓치는 게 이 띠의 함정이야."),
        "mind":   ("원숭이띠는 머리 회전이 빨라 생각이 많아.\n생각이 많으면 잠이 얕아져.",
                   "\"자려는데 자꾸 생각나\"", "생각을 끄는 것도 기술이야. 연습이 필요해."),
    },
    "rooster": {
        "money":  ("닭띠는 씀씀이가 정확해. 어디에 얼마 나갔는지 다 알고 있어.\n대신 남의 씀씀이도 눈에 들어와서 피곤해져.",
                   "\"저걸 왜 저기에 쓰지\"", "남 돈은 남 몫이야. 신경 끄면 편해져."),
        "work":   ("닭띠는 꼼꼼해서 실수가 적어.\n대신 남의 실수도 그냥 못 넘어가.",
                   "\"이건 아닌데\"", "다 맞출 순 없어. 넘길 건 넘겨야 네가 살아."),
        "people": ("닭띠는 할 말은 하는 편이야.\n맞는 말인데 세게 나가서 오해를 살 때가 있어.",
                   "\"틀린 말 한 것도 아닌데\"", "맞는 말도 순서와 온도가 있어."),
        "timing": ("닭띠는 준비가 완벽해야 움직여.\n덕분에 실패는 적은데 시작이 늘 늦어.",
                   "\"아직 다듬을 게 남았어\"", "80퍼센트면 나가도 되는 일이 대부분이야."),
        "mind":   ("닭띠는 자기 기준이 높아.\n그래서 남보다 자기한테 제일 엄해.",
                   "\"이 정도는 당연한 거지\"", "당연한 거 아니야. 잘한 건 잘했다고 해줘."),
    },
    "dog": {
        "money":  ("개띠는 지킬 사람이 있으면 돈 문제에 독해져.\n혼자일 땐 오히려 헐렁해지는 편이야.",
                   "\"나 하나쯤이야\"", "나 하나가 제일 중요한 사람이야."),
        "work":   ("개띠는 맡은 자리에서 책임을 다해.\n대신 부당한 걸 보면 넘기질 못해서 부딪혀.",
                   "\"이건 잘못됐잖아\"", "옳은 걸 말하되 다 이길 필요는 없어."),
        "people": ("개띠는 의리가 있어서 사람을 잘 안 버려.\n그래서 손해를 알면서도 끌고 갈 때가 있어.",
                   "\"내가 여기서 빠지면\"", "네가 빠져도 굴러가. 네가 없어야 굴러가는 것도 있어."),
        "timing": ("개띠는 걱정이 앞서서 최악부터 계산해.\n덕분에 대비는 잘 되는데 시작이 무거워.",
                   "\"잘못되면 어쩌지\"", "대비는 이미 다 했잖아. 이제 가도 돼."),
        "mind":   ("개띠는 남 걱정을 자기 걱정보다 먼저 해.\n정작 본인이 힘든 건 뒤로 미뤄.",
                   "\"나는 나중에 봐도 돼\"", "나중은 안 와. 오늘 좀 챙겨."),
    },
    "pig": {
        "money":  ("돼지띠는 있으면 쓰고 없으면 안 쓰는 담백한 편이야.\n대신 사람 때문에 나가는 돈은 계산을 안 해.",
                   "\"그 사람 사정이 딱해서\"", "딱한 사정은 끝이 없어. 선은 있어야 해."),
        "work":   ("돼지띠는 뒤끝이 없어서 같이 일하기 편한 사람이야.\n대신 정리가 필요한 순간에도 좋게 넘어가려 해.",
                   "\"좋은 게 좋은 거지\"", "좋게 넘긴 게 나중에 더 커져서 돌아와."),
        "people": ("돼지띠는 정이 많고 한번 믿으면 끝까지 믿어.\n그래서 아니라는 신호를 늦게 알아채.",
                   "\"설마 그럴 리가\"", "설마가 몇 번 있었잖아. 이번엔 좀 봐."),
        "timing": ("돼지띠는 서두르지 않아. 흐름에 맡기는 편이야.\n대신 밀어야 할 때도 안 밀어서 놓쳐.",
                   "\"때 되면 되겠지\"", "이번 건은 때를 만들어야 하는 쪽이야."),
        "mind":   ("돼지띠는 웬만해선 화를 안 내.\n대신 쌓였다가 한 번에 터지고 본인이 더 놀라.",
                   "\"내가 왜 이러지\"", "안 쌓이게 조금씩 내보내면 안 터져."),
    },
}

ANGLES = ["money", "work", "people", "timing", "mind"]

# ── 지목 훅 ─────────────────────────────────────────────────
# 첫 줄에서 "너 얘기다"를 만들어야 스크롤이 멈춘다. 날짜로 회전시킨다.
HOOKS = [
    "이 글 본 {sign}, 그냥 넘기지 마.",
    "{sign}인데 요즘 뭘 해도 제자리 같으면 읽어봐.",
    "{sign}, 이거 본인 얘기면 소름 돋을 거야.",
    "지나가다 이 글 걸린 {sign} 있을 거야.",
    "{sign} 중에 요즘 마음이 복잡한 사람 있지.",
    "{sign}, 남들은 모르는 얘기 하나 할게.",
    "{sign}면 한 번쯤 이런 생각 해봤을 거야.",
]

# 인용구 다음에 붙는 연결 문장. 하나로 고정하면 매일 같은 말이 나가 자동 생성 티가 난다.
# 앵글마다 어울리는 결이 달라서 앵글별로 나눠 둔다.
BRIDGES: dict[str, list[str]] = {
    "money": ["이 생각으로 넘긴 게 한두 번이 아닐 거야.",
              "그러다 놓친 자리가 분명 있었을 거고."],
    "work":  ["이러고 넘어간 게 쌓여서 지금이 된 거야.",
              "그 말로 덮어둔 게 한두 개가 아닐걸."],
    "people": ["이 말 삼킨 적, 생각보다 많았을 거야.",
               "그러고 혼자 정리한 밤도 있었을 거고."],
    "timing": ["그러다 남이 먼저 가는 걸 봤을 거야.",
               "이 말 하는 사이에 시기가 지나가더라."],
    "mind":  ["이 생각 안고 며칠 보냈을 거야.",
              "혼자 삼킨 게 쌓였을 거고."],
}

# ── 마무리 유입 문구 ─────────────────────────────────────────
# 홍보가 아니다. 궁금하면 알아서 오게 두는 정도로만 둔다.
# ⚠️ 금지: 무조건·100%·반드시·보장·대박 / 본문 URL / DM 유도(스팸 판정)
CTA_POOL = [
    "내 흐름 자세히 보려면 프로필 링크",
    "생년월일만 있으면 프로필에서 무료로 봐",
    "{sign} 올해 흐름은 프로필에 정리해 뒀어",
    "본인 사주도 같은 식으로 본다. 프로필에 있어",
    "더 궁금하면 프로필 한 번 보고 가",
    "내 띠 흐름은 프로필에서 무료로 확인돼",
    "프로필에 무료로 열어놨어",
    "어떤 시기인지 프로필에서 볼 수 있어",
]

BANNED = ["무조건", "100%", "반드시", "보장", "대박", "확실히", "절대"]

# 2026-08-10 리서치 반영: 반응이 좋은 띠 운세는 출생연도만 나열하지 않고
# ① 오늘의 일진이라는 시의성 ② 바로 적용할 한 가지(돈·관계·건강·행동)
# ③ 답하기 쉬운 한 줄 질문을 결합한다. 단, 소재만 빌리고 운세 근거는 반드시
# saju_v6 정본 엔진(zodiac_seo.make_reading + ganzhi_zodiac)에서 얻는다.
POPULAR_FRAMES = [
    ("money", "돈 흐름", "오늘 {sign}, 돈은 크게 벌리기보다 이 한 곳을 먼저 살펴봐."),
    ("love", "관계 흐름", "오늘 {sign}, 한마디를 먼저 건네면 관계의 결이 달라질 수 있어."),
    ("health", "컨디션 흐름", "오늘 {sign}, 밀어붙이기보다 몸의 신호를 먼저 들어봐."),
    ("overall", "오늘의 선택", "오늘 {sign}, 고민하던 일은 이 기준 하나로 정리해봐."),
]

TONE_ACTIONS = {
    "상승": {
        "money": "미뤄둔 금전 연락이나 정산을 먼저 처리해봐.",
        "love": "고마웠던 사람에게 먼저 안부를 건네봐.",
        "health": "기운이 좋은 시간에 가장 중요한 일을 먼저 끝내봐.",
        "overall": "망설이던 한 가지는 작은 실행부터 시작해봐.",
    },
    "능동": {
        "money": "비교만 하던 선택은 기준을 정해 결론을 내려봐.",
        "love": "애매했던 말은 짧고 분명하게 확인해봐.",
        "health": "무리한 약속 하나를 덜어내고 리듬을 지켜봐.",
        "overall": "내가 정할 수 있는 일부터 순서를 잡아봐.",
    },
    "평온": {
        "money": "새 지출보다 이미 잡은 예산을 지키는 데 집중해봐.",
        "love": "평소 고마웠던 마음을 짧게라도 표현해봐.",
        "health": "평소 루틴을 지키고 수면 시간을 조금 앞당겨봐.",
        "overall": "새 판을 벌이기보다 익숙한 일을 단단히 마무리해봐.",
    },
    "신중": {
        "money": "결제와 약속은 한 번 더 확인한 뒤 처리해봐.",
        "love": "바로 답하기보다 감정을 가라앉힌 뒤 말해봐.",
        "health": "일정을 줄이고 몸이 보내는 신호를 먼저 챙겨봐.",
        "overall": "큰 결정은 오늘 결론 대신 자료를 더 모아봐.",
    },
    "주의": {
        "money": "빌려주거나 계약하는 일은 오늘 한 번 더 미뤄봐.",
        "love": "감정이 올라온 대화는 잠시 멈추고 시간을 둬봐.",
        "health": "피로가 쌓인 시간에는 무리한 약속을 잡지 마.",
        "overall": "중요한 선택은 혼자 확정하지 말고 한 사람에게 물어봐.",
    },
}


def _compact(text: str, limit: int = 66) -> str:
    """AI 카드와 쇼츠에 맞게 정본 문장을 문장 단위로 짧게 쓴다."""
    parts = [p.strip() for p in text.replace("\n", " ").split(". ") if p.strip()]
    out = ""
    for part in parts:
        candidate = f"{out}. {part}" if out else part
        if len(candidate) > limit and out:
            break
        out = candidate
    return out.rstrip(".") + "."


def daily_story(date_iso: str, slug: str | None = None) -> dict:
    """사주v6 정본 계산값으로 하루 한 편(2장) 띠 지목 대본을 만든다.

    출생연도는 스크롤 훅으로만 가끔 쓰고, 대본의 핵심은 당일 간지와 그 띠 지지의
    충·합·삼합·형·파·해·오행 관계에서 나온 make_reading 결과다.
    """
    slug = slug or sign_of(date_iso)
    d = dt.date.fromisoformat(date_iso)
    reading = zs.make_reading(slug, date_iso)  # saju_v6와 동일한 결정론적 엔진
    relation = zodiac_day(slug, d)
    day = day_context(d)
    if relation is None:
        raise ValueError(f"띠 지지 계산 실패: {slug}")

    score_rows = [
        ("money", reading.money_score, reading.money),
        ("love", reading.love_score, reading.love),
        ("health", reading.health_score, reading.health),
        ("overall", reading.overall_score, reading.overall),
    ]
    high = max(score for _, score, _ in score_rows)
    # 동점은 날짜로 회전해 같은 일진에서도 같은 포맷만 반복되지 않게 한다.
    candidates = [row for row in score_rows if row[1] == high]
    focus_key, _, focus_text = candidates[d.toordinal() % len(candidates)]
    frame_map = {key: (label, hook) for key, label, hook in POPULAR_FRAMES}
    focus_label, hook_tpl = frame_map[focus_key]
    hook = hook_tpl.format(sign=reading.sign_ko)
    overall = _compact(reading.overall, 72)
    focus = _compact(focus_text, 76)
    action = TONE_ACTIONS[relation["tone"]][focus_key]
    lucky = f"행운 {reading.tip.replace('오늘의 행운 ', '')} / 숫자 {reading.lucky_num}"

    # 2장 모두 AI가 정확히 렌더할 수 있도록 짧은 문장과 명확한 줄바꿈으로 제한한다.
    card_texts = [
        f"{reading.date_ko} {day['label']}\n{reading.sign_ko} {focus_label}\n{hook}\n\n{overall}",
        f"{reading.sign_ko} 오늘의 포인트\n{focus}\n\n오늘의 실천\n{action}\n\n{lucky}\n프로필에서 내 사주 흐름 확인",
    ]
    narration = [
        f"{reading.date_ko} {day['label']}. {hook} {overall}",
        f"오늘 {reading.sign_ko}의 {focus_label}은 이렇습니다. {focus} 오늘의 실천은 {action} {lucky}. 내 사주 기준 흐름은 프로필에서 확인해 보세요.",
    ]
    caption = (
        f"{reading.date_ko} {day['label']}\n"
        f"{reading.sign_ko} {focus_label}\n\n"
        f"{hook}\n{overall}\n\n"
        f"{focus_label}: {focus}\n"
        f"오늘의 실천: {action}\n"
        f"{lucky}\n\n"
        f"오늘 이 말이 필요한 {reading.sign_ko} 있으면 한마디 남겨줘.\n"
        f"내 사주 기준 흐름은 프로필에서 무료로 볼 수 있어."
    )
    return {
        "date": date_iso, "slug": slug, "sign_ko": reading.sign_ko,
        "day_pillar": day["day_pillar"], "day_branch": day["day_branch"],
        "relation": relation, "tone": relation["tone"], "focus_key": focus_key,
        "focus_label": focus_label, "hook": hook, "overall": overall,
        "focus": focus, "action": action, "lucky": lucky,
        "card_texts": card_texts, "narration": narration, "caption": caption,
    }


def pick_years(slug: str, date_iso: str, n: int = YEARS_SHOWN) -> list[str]:
    """이 띠의 생년 중 지금 활동하는 나이대만 골라 n개. 날짜로 창을 밀어 매번 다르게 뽑는다."""
    _, _, _, years = zs.SLUG_TO_INFO[slug]
    live = [y for y in years if BIRTH_MIN <= int(y) <= BIRTH_MAX]
    if not live:
        live = list(years)
    if len(live) <= n:
        return sorted(live)
    d = dt.date.fromisoformat(date_iso)
    start = d.toordinal() % len(live)
    # 창을 밀어 매번 다른 조합을 뽑되, 보여줄 때는 연도순으로 정렬한다.
    # 정렬하지 않으면 "개띠 2006 · 1958 · 1970" 처럼 나와 읽는 사람이 자기 해를 못 찾는다.
    return sorted(live[(start + i) % len(live)] for i in range(n))


def sign_of(date_iso: str) -> str:
    """12일 주기로 띠를 회전시킨다."""
    return ORDER[dt.date.fromisoformat(date_iso).toordinal() % len(ORDER)]


def angle_of(date_iso: str) -> str:
    """앵글은 5일 주기. 12와 5가 서로소라 같은 (띠,앵글) 짝은 60일마다 온다."""
    return ANGLES[dt.date.fromisoformat(date_iso).toordinal() % len(ANGLES)]


def build_text(date_iso: str, slug: str | None = None) -> str:
    """발행 본문도 카드·쇼츠와 같은 사주v6 일진 계산 결과를 사용한다."""
    text = daily_story(date_iso, slug)["caption"]
    for b in BANNED:
        if b in text:
            raise SystemExit(f"[FAIL] 금지어 '{b}' 가 본문에 있습니다:\n{text}")
    if "http" in text or "www." in text:
        raise SystemExit(f"[FAIL] 본문에 링크가 있습니다(도달 저하):\n{text}")
    return text


def publish(text: str) -> str:
    """일반 게시물로 낸다. 유령글과 달리 계정에 남아야 검색·프로필 유입에 쓰인다."""
    import requests
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ["THREADS_USER_ID"]
    base = f"{GRAPH}/{uid}"

    j = requests.post(f"{base}/threads", timeout=30, data={
        "media_type": "TEXT", "text": text, "access_token": tok}).json()
    cid = j.get("id")
    if not cid:
        raise SystemExit(f"[FAIL] container: {j}")
    time.sleep(3)
    j = requests.post(f"{base}/threads_publish", timeout=30,
                      data={"creation_id": cid, "access_token": tok}).json()
    pid = j.get("id")
    if not pid:
        raise SystemExit(f"[FAIL] publish: {j}")
    return pid


# ── 카드 캐러셀 발행 ─────────────────────────────────────────
# 계정 실측(2026-08-04): 캐러셀 조회 중앙값 48 vs 텍스트 0~4. 형식 차이가 10배 이상이라
# 같은 글이라도 카드로 내보내는 쪽이 맞다. 텍스트는 캡션으로 같이 실어 검색·복사도 살린다.
RAW_BASE = "https://raw.githubusercontent.com/gsdo1004-cloud/sajufortune-cards/main"


def publish_carousel(image_urls: list[str], caption: str) -> str:
    import requests
    tok = os.environ["THREADS_ACCESS_TOKEN"]
    uid = os.environ["THREADS_USER_ID"]
    base = f"{GRAPH}/{uid}"

    def _post(url, data):
        r = requests.post(url, timeout=60, data=data)
        try:
            return r.json()
        except Exception:
            raise SystemExit(f"[FAIL] 비정상 응답 {r.status_code}: {r.text[:200]}")

    children = []
    for u in image_urls:
        j = _post(f"{base}/threads", {
            "media_type": "IMAGE", "image_url": u,
            "is_carousel_item": "true", "access_token": tok})
        cid = j.get("id")
        if not cid:
            raise SystemExit(f"[FAIL] item container: {j}")
        children.append(cid)
        time.sleep(2)

    j = _post(f"{base}/threads", {
        "media_type": "CAROUSEL", "children": ",".join(children),
        "text": caption, "access_token": tok})
    car = j.get("id")
    if not car:
        raise SystemExit(f"[FAIL] carousel container: {j}")
    time.sleep(6)
    j = _post(f"{base}/threads_publish", {"creation_id": car, "access_token": tok})
    pid = j.get("id")
    if not pid:
        raise SystemExit(f"[FAIL] publish: {j}")
    return pid


def main():
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    prepare = "--prepare" in argv      # 카드만 만들고 끝(커밋 스텝이 뒤따른다)
    text_only = "--text-only" in argv  # 카드 없이 텍스트로만 발행(폴백)
    slug = None
    if "--sign" in argv:
        i = argv.index("--sign")
        if i + 1 < len(argv):
            slug = argv[i + 1]
    args = [a for a in argv if not a.startswith("--") and a != slug]
    date_iso = args[0] if args else zs.today_iso()

    story = daily_story(date_iso, slug)
    text = viral.signal_caption(story, story["caption"])
    used = story["slug"]
    print(f"----- {date_iso} 띠 지목 데일리 1편 ({used}/{story['day_pillar']}/{story['focus_key']}) -----")
    print(text)
    print("------------------------")

    # 1단계 — 카드 생성. raw URL 이 살려면 발행 전에 레포에 커밋돼 있어야 한다.
    if prepare:
        import zodiac_signal_card as zsc
        for p in zsc.build(date_iso, slug):
            print(f"[CARD] {p.name} {p.stat().st_size // 1024}KB")
        return

    if dry:
        print("[DRY-RUN] 발행하지 않았습니다.")
        return

    # 멱등 가드 — 러너가 매번 새 체크아웃이라 마커를 레포에 커밋해야 효력이 있다.
    marker = BASE / "cards" / date_iso / "threads_pub_signal.json"
    if marker.exists():
        print(f"[스킵] {date_iso} 띠 지목 게시물 이미 발행됨")
        return

    # 2단계 — 발행. 카드가 있으면 캐러셀, 없으면 텍스트로 떨어진다.
    # 계정 실측상 캐러셀이 텍스트보다 10배 이상 도달하므로 카드를 우선한다.
    cards = [BASE / "cards" / date_iso / f"signal_{i:02d}.jpg" for i in range(1, 3)]
    cards = [card for card in cards if card.is_file()]
    if cards and not text_only:
        urls = [f"{RAW_BASE}/cards/{date_iso}/{p.name}" for p in cards]
        pid = publish_carousel(urls, text)
        kind = f"carousel({len(urls)})"
    else:
        pid = publish(text)
        kind = "text"
    print(f"[OK] signal post: {pid} ({kind})")

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({"post_id": pid, "sign": used, "day_pillar": story["day_pillar"],
                    "focus": story["focus_key"],
                    "kind": kind, "text": text}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
