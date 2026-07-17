# -*- coding: utf-8 -*-
"""띠별운세 Topview GPT Image 2 — 하루 6장 '무실패' 생성 모듈 (2026-07-17 한밝님 지시)

"이 이미지가 실패하면 다른 모든 것이 구현이 안 된다" → 설계 원칙:
  1) 멱등: 검증 통과한 장은 절대 재생성 안 함 → 재실행(2차 스케줄)이 빈 곳만 메움
  2) 사다리 재시도(장당 최대 4회): 정상 프롬프트 ×2 → 단순화 프롬프트 ×2, 지수 백오프
  3) 4중 검증: 파일존재 · 크기(60KB+) · PIL 열림 · 9:16 비율(±)
  4) 잔액 프리플라이트: 부족(<3크레딧)이면 생성 전에 경보
  5) 크레딧부족(4100)·인증만료(401)는 재시도 무의미 → 즉시 중단+경보
  6) 전량/일부 실패해도 발행은 안 죽음: GitHub Actions가 레거시 HTML 카드로 폴백
  7) 복구 2차 경로: 같은 백엔드의 Topview MCP(mcp.topview.ai) — 클로드 세션에서
     `topview_generate_image`로 수동 생성 후 이 모듈 out_dir에 넣으면 검증·이어감

인증: 환경변수 TOPVIEW_UID/TOPVIEW_API_KEY 우선, 없으면 .claude.json의
      topview-mcp 헤더(sk-rGl 유효키)에서 자동 추출 ([[reference_topview_skill]] 정본).
사용: python zodiac_topview.py ensure [YYYY-MM-DD]   # 6장 보장 생성(멱등)
      python zodiac_topview.py status [YYYY-MM-DD]   # 검증 상태만 출력
      python zodiac_topview.py mirror [YYYY-MM-DD]   # G드라이브 일자별 폴더로 복사
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import shutil
import sys
import time
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import zodiac_seo as zs
import zodiac_prompt_engine as zpe
from ganzhi_zodiac import zodiac_day

# Topview 공식 스킬 클라이언트 재사용 (REST api.topview.ai — MCP와 별개 경로)
SKILL_SCRIPTS = Path.home() / ".claude" / "skills" / "topview-skill" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
from shared.client import TopviewClient, TopviewError  # noqa: E402

SUBMIT_PATH = "/v1/common_task/text2image/task/submit"
QUERY_PATH = "/v1/common_task/text2image/task/query"
CREDIT_PATH = "/user/credit/detail"

MODEL = "GPT Image 2"          # 한글 텍스트 렌더링 실증 유일 (2026-07-17)
ASPECT = "9:16"
RESOLUTION = "1K"              # 0.2크레딧/장 → 하루 6장 = 1.2크레딧 (월 36, 잔액 418 = 11개월)
N_CARDS = 6                    # 표지1 + 띠별4 + 12띠요약1(A/B 10초판용)
POLL_TIMEOUT = 300
MIN_BYTES = 60_000             # 1K 9:16 정상물은 수백 KB — 60KB 미만은 깨진 파일
RATIO_RANGE = (0.50, 0.63)     # 9:16 = 0.5625
LOW_CREDIT = 3.0

GDRIVE_DIR = Path(r"G:\내 드라이브\01클로드\작업폴더\띠별운세_이미지")
LOG_FILE = BASE / "zodiac_daily.log"

# 같은 이미지 안에서 한 줄 운세가 겹칠 때 쓰는 기조별 대체 문구 (짧게)
ALT_LINES = {
    "상승": ["운이 활짝 열리는 날", "순풍에 돛 단 흐름", "기회가 문을 두드리는 날"],
    "능동": ["주도권이 내 손에 있는 날", "결단력이 빛나는 날"],
    "평온": ["잔잔하고 무난한 흐름", "안정 속에 복이 깃드는 날"],
    "신중": ["한 박자 쉬어가면 득이 되는 날", "완급 조절이 필요한 날"],
    "주의": ["약속과 일정을 다시 살필 날", "말을 아끼면 복이 되는 날"],
}


def log(msg: str):
    line = f"[{dt.datetime.now().strftime('%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ── 인증 ──────────────────────────────────────────────────────
def _find_mcp_headers(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "topview-mcp" and isinstance(v, dict) and v.get("headers"):
                return v["headers"]
            r = _find_mcp_headers(v)
            if r:
                return r
    elif isinstance(obj, list):
        for it in obj:
            r = _find_mcp_headers(it)
            if r:
                return r
    return None


def _credential_candidates() -> list[tuple[str, str, str]]:
    """(출처명, uid, key) 후보 전부. 우선순위 아닌 '후보 목록' — 검증으로 고른다."""
    out: list[tuple[str, str, str]] = []
    uid_env = os.environ.get("TOPVIEW_UID", "").strip()
    key_env = os.environ.get("TOPVIEW_API_KEY", "").strip()
    if uid_env and key_env:
        out.append(("환경변수", uid_env, key_env))
    try:
        cj = Path.home() / ".claude.json"
        if cj.exists():
            h = _find_mcp_headers(json.loads(cj.read_text(encoding="utf-8")))
            if h:
                k = h.get("Authorization", "").replace("Bearer", "").strip()
                u = h.get("Topview-Uid", "") or h.get("topview-uid", "")
                if u and k:
                    out.append((".claude.json", u, k))
    except (json.JSONDecodeError, OSError) as e:
        log(f"[WARN] .claude.json 파싱 실패: {e}")
    try:
        cf = Path.home() / ".topview" / "credentials.json"
        if cf.exists():
            c = json.loads(cf.read_text(encoding="utf-8"))
            u, k = c.get("uid", "").strip(), c.get("api_key", "").strip()
            if u and k:
                out.append(("credentials.json", u, k))
    except (json.JSONDecodeError, OSError) as e:
        log(f"[WARN] credentials.json 파싱 실패: {e}")
    return out


def _key_alive(uid: str, key: str) -> float | None:
    """잔액 조회로 키 생존 검증. 살아있으면 잔액, 아니면 None."""
    try:
        r = requests.get(f"https://api.topview.ai{CREDIT_PATH}", timeout=20,
                         headers={"Authorization": f"Bearer {key}", "Topview-Uid": uid})
        if r.status_code != 200:
            return None
        return float(r.json()["result"]["remainCredit"])
    except Exception:
        return None


_CRED_CACHE: tuple[str, str] | None = None


def load_credentials() -> tuple[str, str]:
    """살아있는 키를 '실측으로' 골라 반환.

    ⚠️ 2026-07-17 사고: 스킬 config.py는 환경변수를 무조건 1순위로 쓰는데, 이 PC의
    User 스코프 환경변수에 **삭제된 옛 키**(sk-OBojS)가 영구히 박혀 있어서 정상 키를
    가렸다 → REST 전부 401 → "REST가 죽었다"고 3시간 오진. 고정 우선순위를 믿지 말고
    후보를 전부 검증해 살아있는 것을 쓴다. 어느 출처가 죽어도 자동 복구된다.
    """
    global _CRED_CACHE
    if _CRED_CACHE:
        return _CRED_CACHE
    cands = _credential_candidates()
    if not cands:
        raise SystemExit("[FAIL] Topview 자격증명 후보 없음 — .claude.json topview-mcp 확인")
    dead = []
    for src, uid, key in cands:
        credit = _key_alive(uid, key)
        if credit is not None:
            if dead:
                log(f"[WARN] 무효 키 무시: {', '.join(dead)} (출처에서 제거 권장)")
            log(f"인증: {src} 키 사용 (잔액 {credit} 크레딧)")
            _CRED_CACHE = (uid, key)
            return _CRED_CACHE
        dead.append(f"{src}({key[:8]}…)")
    raise SystemExit(f"[FAIL] Topview 키 전부 무효: {', '.join(dead)} — 웹에서 재발급 필요")


def make_client() -> TopviewClient:
    uid, key = load_credentials()
    return TopviewClient(uid=uid, api_key=key)


# ── 운세 데이터 → 이미지용 짧은 문구 ─────────────────────────
def _advice(overall: str, limit: int = 46) -> str:
    """overall("오늘은 갑오일, {리드}. {조언1}. {조언2}") → 조언부만 2~3줄 분량으로.

    ⚠️ 글자수로 자르면 "…보십시" "…단단해집니"처럼 어중간하게 끊긴다(2026-07-17 실측).
    문장 단위로 담되 limit을 넘으면 그 문장은 통째로 버린다.
    """
    parts = [p.strip().rstrip(".") for p in overall.split(". ") if p.strip()]
    sents = parts[1:] if len(parts) > 1 else parts   # [0]=일진 리드 제외
    out = ""
    for s in sents:
        cand = f"{out}. {s}" if out else s
        if len(cand) > limit:
            break
        out = cand
    return (out or sents[0][:limit]) + "."


def build_rows(date_iso: str) -> dict[str, dict]:
    """12띠 각각 {line, advice, lucky, stars{전체/금전/연애/건강}}.

    line   = 짧은 리드 (띠별 3띠 카드용, ≤22자)
    advice = 조언 2~3줄 (12띠 요약 카드 셀용) — 한밝님 레퍼런스 밀도
    lucky  = "흰색·서쪽" 형태 (그날 일진 오행에서 도출 — 명리 근거)
    같은 그룹 내 중복 문구는 회피.
    """
    d = dt.date.fromisoformat(date_iso)
    rows: dict[str, dict] = {}
    # ⚠️ advice는 **12띠 전체**에서 중복을 막아야 한다. 그룹(3띠) 안에서만 막았더니
    # 12띠 요약 카드에서 쥐띠=닭띠, 용띠=개띠로 같은 문장이 나왔다(2026-07-17 실측).
    # 같은 기조(tone)면 문장 풀이 같아 seed가 겹칠 수 있어서다.
    used_advice: set[str] = set()
    for group in zpe.GROUPS:
        used_line: set[str] = set()
        for ko in group:
            slug = zs.KO_TO_SLUG[ko]
            r = zs.make_reading(slug, date_iso)
            ctx = zodiac_day(slug, d)
            line = ctx["lead"].split(" — ")[0].strip().rstrip(".")
            if len(line) > 22:   # 긴 문구 = 이미지 오타 위험 → 기조별 짧은 문구로
                line = ALT_LINES[ctx["tone"]][0]
            if line in used_line:
                for alt in ALT_LINES.get(ctx["tone"], []):
                    if alt not in used_line:
                        line = alt
                        break
            used_line.add(line)

            advice = _advice(r.overall)
            if advice in used_advice:
                # 기조 풀(4~5문장)만으론 부족하다 — 같은 기조를 6띠가 공유하면 바닥난다
                # (7/20 실측 11/12). 같은 tier의 재물·건강·인연 문장까지 후보에 넣어
                # 기조 일관성은 지키면서 후보를 13개로 넓힌다.
                tier = zs._TONE_TIER[ctx["tone"]]
                pool = (zs.TONE_OVERALL[ctx["tone"]] + zs.TONE_MONEY[tier]
                        + zs.TONE_HEALTH[tier] + zs.TONE_LOVE[tier])
                for cand in pool:
                    alt = _advice("일진. " + cand)
                    if alt not in used_advice:
                        advice = alt
                        break
            used_advice.add(advice)

            rows[ko] = {
                "line": line,
                "advice": advice,
                "lucky": f"{ctx['lucky_color']}·{ctx['lucky_direction']}",
                "stars": {"전체": r.overall_score, "금전": r.money_score,
                          "연애": r.love_score, "건강": r.health_score},
                "tone": ctx["tone"],
            }
    return rows


# ── 생성 + 검증 ───────────────────────────────────────────────
def validate_image(path: Path) -> str | None:
    """통과=None, 실패=사유. 4중 검증."""
    if not path.exists():
        return "파일 없음"
    if path.stat().st_size < MIN_BYTES:
        return f"크기 미달({path.stat().st_size}B)"
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            w, h = im.size
    except Exception as e:  # PIL 다양한 예외
        return f"이미지 손상: {e}"
    ratio = w / h
    if not (RATIO_RANGE[0] <= ratio <= RATIO_RANGE[1]):
        return f"비율 이상 {w}x{h}"
    return None


def _download(url: str, out: Path):
    import requests
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    tmp = out.with_suffix(out.suffix + ".part")
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
    tmp.replace(out)


def generate_rest(client: TopviewClient, prompt: str, out: Path,
                  quality: str = "medium") -> None:
    """REST(api.topview.ai) 1회 생성. 실패 시 TopviewError/TimeoutError/requests 예외."""
    body = {"model": MODEL, "prompt": prompt, "aspectRatio": ASPECT,
            "resolution": RESOLUTION, "quality": quality, "generateCount": 1}
    task_id = client.post(SUBMIT_PATH, json=body)["taskId"]
    res = client.poll_task(QUERY_PATH, task_id, interval=4,
                           timeout=POLL_TIMEOUT, verbose=False)
    for img in res.get("images") or []:
        if str(img.get("status", "")).lower() == "success" and img.get("filePath"):
            _download(img["filePath"], out)
            return
    raise TopviewError("NO_IMAGE", f"성공 이미지 없음: {res.get('images')}")


# ── 2차 경로: MCP 게이트웨이(mcp.topview.ai) 직접 호출 ────────
# 2026-07-17 실증: REST 키 세션은 주기 만료(401)되지만 MCP 게이트웨이는
# 같은 sk-rGl 고정키로 살아있음 → 무인 자동화의 생명줄. (역상황도 이력 있음:
# 7/16엔 MCP 404·REST 정상 — 그래서 '둘 다'가 정답)
MCP_URL = "https://mcp.topview.ai/sse"


def _mcp_call_async(tool: str, args: dict, headers: dict, read_timeout: float = 120):
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    async def go():
        async with sse_client(MCP_URL, headers=headers, timeout=30,
                              sse_read_timeout=read_timeout) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(tool, args)
                txt = ""
                for c in res.content:
                    if getattr(c, "type", "") == "text":
                        txt += c.text
                return json.loads(txt)
    return asyncio.run(go())


def _mcp_headers() -> dict:
    uid, key = load_credentials()
    return {"Authorization": f"Bearer {key}", "Topview-Uid": uid}


def generate_mcp(prompt: str, out: Path, quality: str = "medium") -> None:
    """MCP 게이트웨이 1회 생성(submit→poll). 실패 시 TopviewError/TimeoutError."""
    headers = _mcp_headers()
    req = {"taskType": "text_to_image", "model": MODEL, "prompt": prompt,
           "aspectRatio": ASPECT, "resolution": RESOLUTION,
           "quality": quality, "generateCount": 1}
    sub = _mcp_call_async("topview_generate_image", {"req": req}, headers)
    if str(sub.get("code")) != "200":
        raise TopviewError(str(sub.get("code")), f"MCP submit: {sub.get('message')}")
    task_id = sub["result"]["taskId"]
    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT:
        time.sleep(6)
        q = _mcp_call_async("topview_query_task",
                            {"req": {"taskType": "text_to_image", "taskId": task_id,
                                     "needCloudFrontUrl": True}}, headers)
        if str(q.get("code")) != "200":
            raise TopviewError(str(q.get("code")), f"MCP query: {q.get('message')}")
        r = q["result"]
        st = str(r.get("status", "")).lower()
        if st == "success":
            for img in r.get("images") or []:
                if str(img.get("status", "")).lower() == "success" and img.get("filePath"):
                    _download(img["filePath"], out)
                    return
            raise TopviewError("NO_IMAGE", f"MCP 성공인데 이미지 없음: {r.get('images')}")
        if st in ("failed", "fail"):
            raise TopviewError("TASK_FAILED", f"MCP task 실패: {r.get('errorMsg')}")
    raise TimeoutError(f"MCP task {task_id} 시간초과({POLL_TIMEOUT}s)")


FATAL_CODES = {"401", "4100"}   # 인증만료 / 크레딧부족 → 그 경로 재시도 무의미

# 사다리: REST↔MCP 번갈아 + 후반은 단순화 프롬프트 (경로별 치명오류 시 그 경로 제외)
LADDER = [
    ("rest", "prompt", "medium"),
    ("mcp",  "prompt", "medium"),
    ("rest", "simple_prompt", "medium"),
    ("mcp",  "simple_prompt", "medium"),
    ("mcp",  "simple_prompt", "high"),
]


def ensure_one(client: TopviewClient, spec: dict, out: Path,
               alerts: list[str], dead_paths: set[str]) -> bool:
    """한 장을 이중경로 사다리로 보장. 성공=True."""
    if validate_image(out) is None:
        log(f"  [{spec['file']}] 이미 검증 통과 — 건너뜀")
        return True
    tried = 0
    for path, pkey, quality in LADDER:
        if path in dead_paths:
            continue
        tried += 1
        simple = pkey == "simple_prompt"
        try:
            log(f"  [{spec['file']}] 시도 {tried} — {path.upper()}"
                f"(quality={quality}{', 단순화' if simple else ''})")
            if path == "rest":
                generate_rest(client, spec[pkey], out, quality)
            else:
                generate_mcp(spec[pkey], out, quality)
            err = validate_image(out)
            if err is None:
                log(f"  [{spec['file']}] ✅ 성공 ({path.upper()}, 시도 {tried})")
                return True
            log(f"  [{spec['file']}] 검증 실패: {err}")
        except TopviewError as e:
            log(f"  [{spec['file']}] {path.upper()} API 오류 [{e.code}] {e.message[:180]}")
            if str(e.code) in FATAL_CODES:
                dead_paths.add(path)
                alerts.append(f"{path.upper()} 경로 치명 오류 [{e.code}] — 이 경로 중단")
                if str(e.code) == "4100":   # 크레딧 부족은 양쪽 다 무의미
                    dead_paths.update({"rest", "mcp"})
        except requests.HTTPError as e:
            sc = getattr(e.response, "status_code", 0)
            log(f"  [{spec['file']}] {path.upper()} HTTP {sc}")
            if sc in (401, 403):
                dead_paths.add(path)
                alerts.append(f"{path.upper()} 인증 만료(HTTP {sc}) — 이 경로 중단")
        except TimeoutError as e:
            log(f"  [{spec['file']}] {path.upper()} 타임아웃: {e}")
        except Exception as e:   # mcp/네트워크 기타
            log(f"  [{spec['file']}] {path.upper()} 기타: {type(e).__name__}: {str(e)[:180]}")
        if dead_paths >= {"rest", "mcp"}:
            break
        time.sleep(min(5 * tried, 20))
    alerts.append(f"{spec['file']} 생성 실패(시도 {tried}회)")
    return False


def check_balance(client: TopviewClient, alerts: list[str]) -> float | None:
    try:
        credit = float(client.get(CREDIT_PATH)["remainCredit"])
        log(f"잔액: {credit} 크레딧")
        if credit < LOW_CREDIT:
            alerts.append(f"Topview 크레딧 부족 임박: {credit} (하루 1.0 소모)")
        return credit
    except Exception as e:
        log(f"[WARN] 잔액 조회 실패(생성은 계속): {e}")
        return None


def ensure_daily_images(date_iso: str | None = None) -> dict:
    """하루 6장(표지1+띠별4+12띠요약1) 보장 생성(멱등). 반환: {date, ok, files, failed, alerts}."""
    date_iso = date_iso or zs.today_iso()
    d = dt.date.fromisoformat(date_iso)
    out_dir = BASE / "cards" / date_iso
    out_dir.mkdir(parents=True, exist_ok=True)

    log(f"=== 띠별운세 이미지 {N_CARDS}장 보장 생성: {date_iso} ===")
    alerts: list[str] = []
    client = make_client()
    check_balance(client, alerts)

    rows = build_rows(date_iso)
    ds = zpe.daily_set(d, rows)
    t = ds["theme"]
    log(f"오늘 조합: [{t['style'][0]}] 배경={t['bg'][0]} 컨셉={t['concept'][0]} 색={t['palette'][0]}")

    files, failed = [], []
    dead_paths: set[str] = set()
    for i, spec in enumerate(ds["images"], 1):
        out = out_dir / f"card_{i:02d}.png"
        if ensure_one(client, spec, out, alerts, dead_paths):
            files.append(str(out))
        else:
            failed.append(spec["file"])
            if dead_paths >= {"rest", "mcp"}:
                break   # 두 경로 다 죽음(401/4100) → 나머지도 무의미

    ok = not failed
    log(f"=== 결과: {len(files)}/{N_CARDS} 성공"
        f"{' | 실패: ' + ', '.join(failed) if failed else ''} ===")
    return {"date": date_iso, "ok": ok, "files": files,
            "failed": failed, "alerts": alerts}


# ── G드라이브 미러 (틱톡·blog-auto 소스) ─────────────────────
KOREAN_NAMES = ["01_표지", "02_띠별A", "03_띠별B", "04_띠별C", "05_띠별D", "06_12띠요약"]


def mirror_to_gdrive(date_iso: str | None = None) -> bool:
    """cards/{date}/card_01~05.png → G드라이브 일자별 폴더(한글명). 실패해도 파이프라인 지속."""
    date_iso = date_iso or zs.today_iso()
    src = BASE / "cards" / date_iso
    try:
        dst = GDRIVE_DIR / date_iso
        dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for i, name in enumerate(KOREAN_NAMES, 1):
            s = src / f"card_{i:02d}.png"
            if s.exists() and validate_image(s) is None:
                shutil.copy2(s, dst / f"{name}.png")
                n += 1
        log(f"G드라이브 미러: {n}/{N_CARDS}장 → {dst}")
        return n == N_CARDS
    except OSError as e:
        log(f"[WARN] G드라이브 미러 실패(파이프라인 지속): {e}")
        return False


def status(date_iso: str | None = None) -> dict:
    date_iso = date_iso or zs.today_iso()
    out_dir = BASE / "cards" / date_iso
    st = {}
    for i, name in enumerate(KOREAN_NAMES, 1):
        p = out_dir / f"card_{i:02d}.png"
        err = validate_image(p)
        st[name] = "OK" if err is None else err
    return st


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mode = sys.argv[1] if len(sys.argv) > 1 else "ensure"
    di = sys.argv[2] if len(sys.argv) > 2 else None
    if mode == "ensure":
        r = ensure_daily_images(di)
        mirror_to_gdrive(r["date"])
        if r["alerts"]:
            print("ALERTS:", " / ".join(r["alerts"]))
        sys.exit(0 if r["ok"] else 1)
    elif mode == "status":
        for k, v in status(di).items():
            print(f"{k}: {v}")
    elif mode == "mirror":
        sys.exit(0 if mirror_to_gdrive(di) else 1)
    else:
        raise SystemExit("사용법: python zodiac_topview.py [ensure|status|mirror] [YYYY-MM-DD]")
