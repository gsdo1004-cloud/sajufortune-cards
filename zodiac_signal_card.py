# -*- coding: utf-8 -*-
"""띠 지목 카드뉴스 생성 — Topview GPT Image 2 일일 생성 + 안전 PIL 폴백.

2026-08-05에는 배경 고정+PIL 텍스트로 바꿨다. 그 전 Topview GPT Image 2가 한글까지
그리던 방식에서 2026-07-30 한글 깨짐 사고가 실제로 있었기 때문이다. 이번에는 매일 새
AI 이미지로 되돌리되, 그 사고를 반복하지 않도록 다음 안전장치를 둔다.

  · 카드당 최대 4회: 정상 프롬프트 2회 → 단순화 프롬프트 2회.
  · 파일 존재·60KB 이상·PIL 열림·9:16 비율을 모두 통과해야 채택한다.
  · Topview 잔액이 3 크레딧 미만이거나 401/4100이 나오면 즉시 AI 생성을 중단하고 경보다.
  · AI 카드의 한글은 완전 자동 판독이 어려워, 매일 `signal_ai_manifest.json`과 로그에
    **육안 확인 필요**를 남긴다. 이미지/API 검증 실패 시에는 그 날짜 5장을 기존 PIL 방식으로
    즉시 다시 만들어 한글이 깨진 카드를 발행하지 않는다.

매일 5장을 새로 생성하므로 현재 1K 기준 약 1.0 Topview 크레딧/일(단가 변동 가능)이 든다.

실행:
  python zodiac_signal_card.py 2026-08-06            # cards/2026-08-06/signal_01..05.png
  python zodiac_signal_card.py 2026-08-06 --sign dog
"""
from __future__ import annotations
import json
import os
import sys
import time
import datetime as dt
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

import zodiac_seo as zs
import zodiac_signal as zsig
import zodiac_topview as zt

BASE = Path(__file__).resolve().parent
BG_DIR = BASE / "assets" / "bg"
FONT_DIR = BASE / "assets" / "fonts"

W, H = 1080, 1920          # 9:16 — 기존 띠별 카드와 같은 비율로 맞춘다
PANEL_ALPHA = 218          # 배경이 복잡해도 글자가 읽히게 하는 최소치(실측으로 조정)
AI_MANIFEST = "signal_ai_manifest.json"
AI_CREDIT_PER_CARD = 0.2   # 현재 GPT Image 2 1K 실측 단가. Topview 정책에 따라 변동 가능.

# 러너(ubuntu)에도 있어야 하므로 폰트는 레포에 동봉한다. 없으면 시스템 폰트로 떨어진다.
_FALLBACK = ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
             "C:/Windows/Fonts/malgun.ttf"]


def F(name: str, size: int):
    p = FONT_DIR / name
    if p.exists():
        return ImageFont.truetype(str(p), size)
    for f in _FALLBACK:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def wrap(dr, text: str, font, max_w: int) -> list[str]:
    """한글은 어절 단위로 끊는다(word-break: keep-all 과 같은 의도)."""
    out, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if dr.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out


def bg_for(slug: str, variant: int) -> Image.Image:
    """배경 1장을 줌·이동으로 변주한다. 5장이 같은 그림으로 안 보이게 하는 장치."""
    src = BG_DIR / f"bg_{slug}.jpg"
    if not src.exists():
        im = Image.new("RGB", (W, H), (226, 236, 247))
    else:
        im = Image.open(src).convert("RGB")
    # 커버 리사이즈
    sc = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)

    zoom, dy = [(1.00, 0.0), (1.08, -0.04), (1.14, 0.06),
                (1.10, -0.02), (1.04, 0.03)][variant % 5]
    if zoom > 1.0:
        nw, nh = int(im.width * zoom), int(im.height * zoom)
        im = im.resize((nw, nh), Image.LANCZOS)
    ox = (im.width - W) // 2
    oy = int((im.height - H) // 2 + H * dy)
    oy = max(0, min(oy, im.height - H))
    return im.crop((ox, oy, ox + W, oy + H))


def panel(dr, top: int, bottom: int, pad: int = 60):
    dr.rounded_rectangle([pad, top, W - pad, bottom], radius=48,
                         fill=(255, 255, 255, PANEL_ALPHA))


def card_cover(slug: str, sign_ko: str, years: str, hook: str) -> Image.Image:
    im = bg_for(slug, 0)
    dr = ImageDraw.Draw(im, "RGBA")
    f_sign = F("GowunBatang-Bold.ttf", 132)
    f_year = F("Pretendard-Black.ttf", 54)
    f_hook = F("Pretendard-Black.ttf", 52)

    y = 190
    tw = dr.textlength(sign_ko, font=f_sign)
    # 제목은 패널 없이 얹되 흰 테두리로 배경과 분리한다(밝은 배경이라 검정 글자가 산다).
    dr.text(((W - tw) / 2, y), sign_ko, font=f_sign, fill=(26, 26, 46),
            stroke_width=10, stroke_fill=(255, 255, 255))
    y += 172
    # 생년이 5개라 한 줄이 길다 — 폭에 맞을 때까지 폰트를 줄인다(잘리는 것보다 낫다).
    sz = 54
    for sz in (54, 48, 43, 39, 35):
        f_year = F("Pretendard-Black.ttf", sz)
        yw = dr.textlength(years, font=f_year)
        if yw <= W - 210:
            break
    dr.rounded_rectangle([(W - yw) / 2 - 34, y - 12, (W + yw) / 2 + 34, y + sz + 20],
                         radius=42, fill=(232, 75, 138))
    dr.text(((W - yw) / 2, y), years, font=f_year, fill=(255, 255, 255))

    y += sz + 96
    lines = wrap(dr, hook, f_hook, W - 240)
    panel(dr, y - 34, y + len(lines) * 72 + 26)
    for ln in lines:
        lw = dr.textlength(ln, font=f_hook)
        dr.text(((W - lw) / 2, y), ln, font=f_hook, fill=(26, 26, 46))
        y += 72
    return im


def card_text(slug: str, variant: int, body: str, color=(70, 70, 86),
              font_name="NanumGothic-Regular.ttf", size=52,
              stroke=False) -> Image.Image:
    im = bg_for(slug, variant)
    dr = ImageDraw.Draw(im, "RGBA")
    f = F(font_name, size)
    lines: list[str] = []
    for para in body.split("\n"):
        lines += wrap(dr, para, f, W - 260) if para.strip() else [""]
    lh = int(size * 1.62)
    block = len(lines) * lh
    top = int(H * 0.30) - 40
    panel(dr, top, top + block + 80)
    y = top + 40
    for ln in lines:
        if ln:
            lw = dr.textlength(ln, font=f)
            if stroke:
                dr.text(((W - lw) / 2, y), ln, font=f, fill=color,
                        stroke_width=3, stroke_fill=(255, 255, 255))
            else:
                dr.text(((W - lw) / 2, y), ln, font=f, fill=color)
        y += lh
    return im


def card_quote(slug: str, quote: str, bridge: str) -> Image.Image:
    im = bg_for(slug, 2)
    dr = ImageDraw.Draw(im, "RGBA")
    f_q = F("NanumPenScript-Regular.ttf", 96)
    f_b = F("NanumGothic-Regular.ttf", 46)
    top = int(H * 0.30)
    b_lines = wrap(dr, bridge, f_b, W - 260)
    panel(dr, top - 40, top + 150 + len(b_lines) * 70)

    qw = dr.textlength(quote, font=f_q)
    # 형광펜 — 글자 아래쪽 절반에 깔아 밑줄처럼 보이게 한다.
    dr.rectangle([(W - qw) / 2 - 18, top + 66, (W + qw) / 2 + 18, top + 112],
                 fill=(251, 192, 218))
    dr.text(((W - qw) / 2, top + 10), quote, font=f_q, fill=(40, 30, 40))
    y = top + 150
    for ln in b_lines:
        lw = dr.textlength(ln, font=f_b)
        dr.text(((W - lw) / 2, y), ln, font=f_b, fill=(95, 95, 110))
        y += 70
    return im


def card_cta(slug: str, sign_ko: str, cta: str) -> Image.Image:
    im = bg_for(slug, 4)
    dr = ImageDraw.Draw(im, "RGBA")
    f_t = F("GowunBatang-Bold.ttf", 66)
    f_c = F("Pretendard-Black.ttf", 44)
    top = int(H * 0.32)
    lines = wrap(dr, cta, f_c, W - 260)
    panel(dr, top - 40, top + 130 + len(lines) * 66)
    t = f"{sign_ko}의 흐름"
    tw = dr.textlength(t, font=f_t)
    dr.text(((W - tw) / 2, top + 6), t, font=f_t, fill=(26, 26, 46))
    y = top + 130
    for ln in lines:
        lw = dr.textlength(ln, font=f_c)
        dr.text(((W - lw) / 2, y), ln, font=f_c, fill=(200, 40, 90))
        y += 66
    return im


def build_pil_fallback(date_iso: str, slug: str | None = None) -> list[Path]:
    """AI 생성이 불가하거나 검증에 실패한 **그 날짜만** 쓰는 한글 안전 폴백."""
    slug = slug or zsig.sign_of(date_iso)
    d = dt.date.fromisoformat(date_iso)
    sign_ko = zs.SLUG_TO_INFO[slug][1]
    if not sign_ko.endswith("띠"):
        sign_ko += "띠"

    angle = zsig.angle_of(date_iso)
    trait, quote, turn = zsig.TRAITS[slug][angle]
    years = " · ".join(zsig.pick_years(slug, date_iso))
    hook = zsig.HOOKS[d.toordinal() % len(zsig.HOOKS)].format(sign=sign_ko)
    bridges = zsig.BRIDGES[angle]
    bridge = bridges[d.toordinal() % len(bridges)]
    cta = zsig.CTA_POOL[d.toordinal() % len(zsig.CTA_POOL)].format(sign=sign_ko)

    out_dir = BASE / "cards" / date_iso
    out_dir.mkdir(parents=True, exist_ok=True)
    imgs = [
        card_cover(slug, sign_ko, years, hook),
        card_text(slug, 1, trait),
        card_quote(slug, quote, bridge),
        card_text(slug, 3, turn, color=(200, 40, 90),
                  font_name="GowunBatang-Bold.ttf", size=60),
        card_cta(slug, sign_ko, cta),
    ]
    # JPEG 로 저장한다 — PNG 는 장당 3MB 라 5장이면 15MB 다. 매일 쌓이면 레포가 감당 못 하고
    # 러너 체크아웃도 느려진다. 사진형 일러스트라 JPEG 손실이 눈에 띄지 않는다.
    paths = []
    for i, im in enumerate(imgs, 1):
        p = out_dir / f"signal_{i:02d}.jpg"
        im.convert("RGB").save(p, "JPEG", quality=88, optimize=True, progressive=True)
        paths.append(p)
    return paths


class SignalTopviewError(RuntimeError):
    """GitHub Actions에서도 쓸 수 있는 Topview REST 오류 표현."""

    def __init__(self, code: str, message: str):
        self.code = str(code)
        self.message = str(message)
        super().__init__(f"[{self.code}] {self.message}")


class SignalTopviewClient:
    """zodiac_topview.py의 REST submit→poll 패턴을 그대로 쓰는 최소 클라이언트.

    zodiac_topview의 공식 스킬 클라이언트는 집 PC의 ~/.claude 경로에만 있으므로,
    Actions에서는 같은 REST 규약을 이 작은 클라이언트로 호출한다.
    """

    BASE_URL = "https://api.topview.ai"

    def __init__(self, uid: str, api_key: str):
        self.headers = {"Topview-Uid": uid, "Authorization": f"Bearer {api_key}"}

    @staticmethod
    def _result(response: requests.Response) -> dict:
        response.raise_for_status()
        data = response.json()
        code = str(data.get("code", ""))
        if code != "200":
            raise SignalTopviewError(code or "UNKNOWN", data.get("message", str(data)))
        return data.get("result", data)

    def get(self, path: str, *, params: dict | None = None, timeout: int = 30) -> dict:
        return self._result(requests.get(f"{self.BASE_URL}{path}", headers=self.headers,
                                         params=params, timeout=timeout))

    def post(self, path: str, *, json_body: dict, timeout: int = 30) -> dict:
        return self._result(requests.post(f"{self.BASE_URL}{path}", headers=self.headers,
                                          json=json_body, timeout=timeout))


def _alert(message: str):
    """로그·Actions 경고·가능한 경우 메일 경보를 함께 남긴다."""
    print(f"[ALERT] {message}")
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning::{message}")
    try:
        import zodiac_alert
        zodiac_alert.alert("띠 지목 Topview 생성 경보", message)
    except Exception:
        pass


def _write_manifest(out_dir: Path, payload: dict):
    (out_dir / AI_MANIFEST).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                       encoding="utf-8")


def _signal_texts(date_iso: str, slug: str) -> tuple[str, str, list[str]]:
    """카드/나레이션과 같은 5개 문구를 뽑아 AI 프롬프트에도 그대로 넣는다."""
    d = dt.date.fromisoformat(date_iso)
    sign_ko = zs.SLUG_TO_INFO[slug][1]
    if not sign_ko.endswith("띠"):
        sign_ko += "띠"
    angle = zsig.angle_of(date_iso)
    trait, quote, turn = zsig.TRAITS[slug][angle]
    years = " · ".join(zsig.pick_years(slug, date_iso))
    hook = zsig.HOOKS[d.toordinal() % len(zsig.HOOKS)].format(sign=sign_ko)
    bridge = zsig.BRIDGES[angle][d.toordinal() % len(zsig.BRIDGES[angle])]
    cta = zsig.CTA_POOL[d.toordinal() % len(zsig.CTA_POOL)].format(sign=sign_ko)
    return sign_ko, angle, [
        f"{sign_ko}\n{years}\n{hook}",
        trait,
        f"{quote}\n{bridge}",
        turn,
        cta,
    ]


def _prompt(sign_ko: str, angle: str, text: str, index: int, *, simple: bool) -> str:
    """한글 깨짐을 줄이기 위해 글자·줄바꿈·금지사항을 반복해 명시한다."""
    layout = (
        "Use one centered translucent ivory text panel, high contrast black Hangul, "
        "large clean Korean editorial typography, ample line spacing."
        if simple else
        "Use a premium Korean fortune editorial layout: refined zodiac illustration, "
        "cinematic traditional Korean colors, a clean central text panel, and elegant hierarchy."
    )
    return f"""Create one vertical 9:16 social card for a Korean zodiac fortune channel.
Card {index}/5, subject: {sign_ko}, theme: {angle}. {layout}

CRITICAL TEXT REQUIREMENT: Render the following Korean Hangul text EXACTLY as written.
Preserve every character, spacing, punctuation, quotation mark, and line break. The text must
be crisp, readable Korean Hangul. Do not translate, paraphrase, omit, replace with Latin text,
or produce gibberish. Do not add any other words, date, logo, watermark, or signature.

EXACT KOREAN TEXT START
{text}
EXACT KOREAN TEXT END

The final image must contain only this exact Korean text and visual artwork. No English text."""


def _download(url: str, out: Path):
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    tmp = out.with_suffix(out.suffix + ".part")
    with open(tmp, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            f.write(chunk)
    tmp.replace(out)


def _normalize_jpeg(path: Path):
    """Topview 원본 포맷과 무관하게 signal_*.jpg 계약을 실제 JPEG로 맞춘다.

    텍스트를 다시 그리지 않고 인코딩만 바꾸므로, AI가 렌더한 한글·구성은 그대로 유지된다.
    """
    tmp = path.with_suffix(".jpg.part")
    with Image.open(path) as image:
        image.convert("RGB").save(tmp, "JPEG", quality=92, optimize=True, progressive=True)
    tmp.replace(path)


def _generate_rest(client: SignalTopviewClient, prompt: str, out: Path):
    body = {
        "model": zt.MODEL,
        "prompt": prompt,
        "aspectRatio": zt.ASPECT,
        "resolution": zt.RESOLUTION,
        "quality": "medium",
        "generateCount": 1,
    }
    task_id = client.post(zt.SUBMIT_PATH, json_body=body)["taskId"]
    started = time.time()
    while time.time() - started < zt.POLL_TIMEOUT:
        result = client.get(zt.QUERY_PATH, params={"taskId": task_id})
        status = str(result.get("status", "")).lower()
        if status == "success":
            for image in result.get("images") or []:
                if str(image.get("status", "")).lower() == "success" and image.get("filePath"):
                    _download(image["filePath"], out)
                    return
            raise SignalTopviewError("NO_IMAGE", "성공 응답에 이미지가 없습니다")
        if status in ("failed", "fail"):
            raise SignalTopviewError("TASK_FAILED", result.get("errorMsg", "작업 실패"))
        time.sleep(4)
    raise TimeoutError(f"Topview task {task_id} 시간초과({zt.POLL_TIMEOUT}s)")


def _check_credit(client: SignalTopviewClient) -> float:
    credit = float(client.get(zt.CREDIT_PATH).get("remainCredit", 0))
    print(f"[Topview] 띠 지목 잔액: {credit} 크레딧 (오늘 5장 약 {AI_CREDIT_PER_CARD * 5:.1f})")
    if credit < zt.LOW_CREDIT:
        raise SignalTopviewError("4100", f"잔액 부족 {credit} < {zt.LOW_CREDIT}")
    return credit


def _is_fatal(exc: BaseException) -> bool:
    if isinstance(exc, SignalTopviewError):
        return exc.code in {"401", "403", "4100"}
    return (isinstance(exc, requests.HTTPError)
            and getattr(exc.response, "status_code", 0) in {401, 403})


def _generate_one(client: SignalTopviewClient, out: Path, sign_ko: str, angle: str,
                  text: str, index: int):
    """정상×2 → 단순화×2. 치명 오류는 호출자에게 즉시 올린다."""
    ladder = [(False, "정상"), (False, "정상"), (True, "단순화"), (True, "단순화")]
    failures: list[str] = []
    for attempt, (simple, label) in enumerate(ladder, 1):
        try:
            print(f"[Topview] signal_{index:02d} 시도 {attempt}/4 — {label} 프롬프트")
            _generate_rest(client, _prompt(sign_ko, angle, text, index, simple=simple), out)
            _normalize_jpeg(out)
            err = zt.validate_image(out)  # 파일·60KB·PIL 열림·9:16 검증을 정본 그대로 재사용
            if err is None:
                print(f"[Topview] signal_{index:02d} 검증 통과")
                return
            failures.append(f"검증 실패: {err}")
            print(f"[Topview] signal_{index:02d} 검증 실패: {err}")
        except Exception as exc:  # 네트워크/태스크 실패는 다음 사다리로, 401·4100은 즉시 중단
            if _is_fatal(exc):
                raise
            failures.append(f"{type(exc).__name__}: {str(exc)[:160]}")
            print(f"[Topview] signal_{index:02d} 실패: {failures[-1]}")
        time.sleep(min(5 * attempt, 15))
    raise RuntimeError(" / ".join(failures) or "Topview 생성 실패")


def build(date_iso: str, slug: str | None = None) -> list[Path]:
    """매일 새 AI 카드 5장을 생성하고, 위험 신호가 나면 해당 날짜만 PIL로 대체한다."""
    slug = slug or zsig.sign_of(date_iso)
    out_dir = BASE / "cards" / date_iso
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"signal_{i:02d}.jpg" for i in range(1, 6)]
    manifest_path = out_dir / AI_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    if (manifest.get("generator") in {"topview_gpt_image_2", "pil_fallback"}
            and all(zt.validate_image(path) is None for path in paths)):
        print(f"[Topview] {date_iso} 기존 카드 5장 검증 통과({manifest.get('generator')}) — 재생성 건너뜀")
        return paths

    sign_ko, angle, texts = _signal_texts(date_iso, slug)
    try:
        uid, key = zt.load_credentials()
        client = SignalTopviewClient(uid, key)
        _check_credit(client)
        print(f"[Topview] 띠 지목 AI 생성 시작: {date_iso}, 5장, 예상 약 {AI_CREDIT_PER_CARD * 5:.1f} 크레딧")
        for index, (out, text) in enumerate(zip(paths, texts), 1):
            _generate_one(client, out, sign_ko, angle, text, index)
    except BaseException as exc:
        reason = f"{type(exc).__name__}: {str(exc)[:300]}"
        _alert(f"{date_iso} 띠 지목 Topview 생성 중단 — {reason}. 기존 PIL 카드로 폴백합니다.")
        paths = build_pil_fallback(date_iso, slug)
        _write_manifest(out_dir, {
            "date": date_iso, "generator": "pil_fallback", "reason": reason,
            "review_required": False, "cards": [path.name for path in paths],
        })
        return paths

    _write_manifest(out_dir, {
        "date": date_iso,
        "generator": "topview_gpt_image_2",
        "estimated_credit": AI_CREDIT_PER_CARD * 5,
        "cards": [path.name for path in paths],
        "review_required": True,
        "review_reason": "AI 생성 한글은 완전 자동 판독이 불가합니다. 발행 전 글자 깨짐을 육안 확인하세요.",
    })
    print(f"[REVIEW REQUIRED] {date_iso} 띠 지목 AI 카드의 한글 텍스트를 육안 확인하세요: {manifest_path}")
    return paths


def main():
    argv = sys.argv[1:]
    slug = None
    if "--sign" in argv:
        i = argv.index("--sign")
        if i + 1 < len(argv):
            slug = argv[i + 1]
    args = [a for a in argv if not a.startswith("--") and a != slug]
    date_iso = args[0] if args else zs.today_iso()
    for p in build(date_iso, slug):
        print(f"[OK] {p.relative_to(BASE)}  {p.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
