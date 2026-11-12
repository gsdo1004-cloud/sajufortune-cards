"""12지신 비주얼 로테이션 2.0 — 공유 무비용 결정론적 정책.

실제 이미지 호출/유료 API 호출 없음. 날짜+채널+슬롯에 따라 일관된 화풍 반환.
동물/띠 정체성은 어떤 화풍에서도 유지한다. 로컬/외부 플랫폼 독립 실행 가능.
"""
from __future__ import annotations
import datetime as dt
import re

STYLES = (
    {"id":"golden_guardian","name":"황금 신수","prompt":"Epic golden guardian spirit key art, monumental mythic Korean zodiac animal, luminous gold dawn beams, floating auspicious clouds, premium realistic fantasy textures, dynamic wide cinematic scale, no human host","bg":"#2F254B","accent":"#D49C3F","icon":"#FFF1C9","paper":"#FFFAF0"},
    {"id":"cute_3d","name":"귀여운 3D","prompt":"Premium charming three-dimensional animated zodiac animal character with expressive friendly eyes, soft tactile fur or elegant scales, warm studio lighting, playful meaningful body language, cohesive original character design, no human host","bg":"#E9D9FB","accent":"#7745B6","icon":"#F1E7FF","paper":"#FFFFFF"},
    {"id":"modern_life","name":"현대생활 12지신","prompt":"Original anthropomorphic zodiac-animal character in a relatable present-day Korean office or street vignette, species recognizably animal with coherent animal anatomy and expressive gestures, cinematic slice-of-life storytelling, never a human model in hanbok","bg":"#DCEEF5","accent":"#206E94","icon":"#D6EFFB","paper":"#FCFEFF"},
    {"id":"awakening","name":"신수 변신","prompt":"Dynamic visual storytelling of the same zodiac animal awakening into its benevolent spirit-guardian form, swirling auspicious light trail and transformation energy, dramatic contrast, coherent animal identity before and after, no horror, no human face","bg":"#E9E1FC","accent":"#6844A2","icon":"#E7DFFF","paper":"#FAF7FF"},
    {"id":"nature_cinema","name":"자연·영화적 실사","prompt":"Lifelike cinematic zodiac animal in luminous Korean mountain forest, ocean, meadow or mist, natural sunlight and authentic animal posture, clear species silhouette, aspirational calm visual narrative, real-world photographic composition without human actors","bg":"#DFEEDC","accent":"#3D7954","icon":"#E6F3DA","paper":"#FCFFF9"},
    {"id":"cyber_future","name":"미래도시 네온","prompt":"Elegant original East Asian zodiac animal spirit traversing an imagined futuristic Korean city with crisp teal and violet neon, refined science-fantasy design, cinematic high contrast, distinctive animal silhouette, no humanoid fashion model","bg":"#DADFFF","accent":"#5356B1","icon":"#E9E7FF","paper":"#FCFCFF"},
    {"id":"minhwa_ink","name":"한국 민화·수묵","prompt":"Distinctive traditional Korean minhwa and ink-wash interpretation with authentic animal iconography, handmade paper fibers, brushstroke clouds and pine trees, warm obangsaek accents, elegant contemporary editorial framing, no recurring hanbok presenter","bg":"#F5E7D3","accent":"#965A3D","icon":"#FAECD9","paper":"#FFFCF5"},
    {"id":"golden_symbols","name":"황금 오브제","prompt":"Luxury Korean zodiac emblem still life, a detailed recognizable animal-shaped golden sculpture beside lucky coins, moonlit celestial calendar motifs and soft auspicious light, high-end editorial product photography, animal remains clearly identifiable, no human host","bg":"#F3E4BF","accent":"#9B742B","icon":"#FDF3D2","paper":"#FFFBF1"},
)
STYLE_BY_ID={s["id"]:s for s in STYLES}
ANIMAL_GUARD=(
    "The twelve Korean zodiac species must remain distinct in their correct order when all are present: "
    "rat, ox, tiger, rabbit, traditional East Asian dragon, snake, horse, sheep, monkey, rooster, dog, pig. "
    "The dragon has a long serpentine body and horns without Western bat wings. "
    "Rat is charming and clean, never vermin, sewage or horror. "
    "Snake is gentle and elegant, never fangs, prey or strike pose. "
    "No generic Korean hanbok woman as the main subject, no celebrity, no duplicate species, "
    "no grotesque hybrid, no extra limbs, no text within the generated illustration."
)

def _day(value=None):
    if isinstance(value, dt.datetime):return value.date()
    if isinstance(value, dt.date):return value
    if value:
        raw=str(value)
        match=re.search(r"(20\d\d)[-_]?([01]\d)[-_]?([0-3]\d)",raw)
        if match:
            try:return dt.date(*(int(x) for x in match.groups()))
            except ValueError:pass
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()

def style_for(value=None, channel="daily", slot=0):
    day=_day(value)
    # 매주 동적 위상 이동, 주간 7일에 7계열, 격주 8번째까지 순환.
    cycle=(day.toordinal()//7+day.weekday()+int(slot))%len(STYLES)
    return dict(STYLES[cycle])

def art_direction(value=None, channel="daily", slot=0):
    style=style_for(value,channel=channel,slot=slot)
    return (f"Visual rotation 2.0 family [{style['id']} / {style['name']}]. "
            f"{style['prompt']}. {ANIMAL_GUARD} "
            "Strong first-frame silhouette, mobile-safe center focal point, "
            "clear margin for externally composed readable Korean caption and subtitles.")

def css_palette(value=None,channel="cardnews",slot=0):
    return style_for(value,channel=channel,slot=slot)
