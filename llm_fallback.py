# -*- coding: utf-8 -*-
"""LLM 호출 공용 창구 — Gemini 우선, 막히면 로컬 Ollama (2026-07-27 신설).

왜 필요한가
-----------
Gemini 무료키 하나를 여러 파이프라인(AI뉴스·블로그·대본·사주)이 공유한다.
분당 한도가 있어 한 곳이 쓰면 다른 곳이 429 를 맞는다. 실제로 2026-07-27
AI 뉴스 발행에서 2건째부터 해석문이 통째로 빠졌다.

이 집 PC 에는 Ollama 와 모델이 이미 설치돼 있는데 안 쓰고 있었다.
RTX 4070 12GB, qwen2.5:14b 실측 9초/건, 한국어 품질 사용 가능 수준.
쿼터가 없으니 429 를 맞을 일이 없다.

⚠️ GitHub Actions 러너에서는 로컬 Ollama 에 접근할 수 없다(당연히).
   러너에서는 Gemini 만 쓰고 실패 시 None 을 돌려준다 — 호출부는 그 경우
   자체 폴백(사실만 발행 등)을 갖고 있어야 한다.

사용:
    from llm_fallback import ask
    text = ask("프롬프트")          # str 또는 None
"""
from __future__ import annotations

import json
import os
import time

import requests

GEMINI_MODEL = "gemini-3.5-flash"
OLLAMA_URL = "http://localhost:11434"
# 실측(2026-07-27): qwen2.5:14b 9초/건, 한국어 존댓말 정상.
# gemma4:12b-it-qat 은 40~98초에 빈 응답이라 쓰지 않는다.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")

_ollama_alive: bool | None = None      # 매번 재확인하면 느리다 — 프로세스당 1회


def _log(m: str):
    print(f"[llm] {m}", flush=True)


def _gemini(prompt: str, max_tokens: int, temperature: float,
            key: str | None = None) -> tuple[str | None, bool]:
    """(결과, 재시도할_가치_있음) — 429 면 잠시 뒤 다시 칠 가치가 있다."""
    key = key or os.environ.get("GEMINI_API_KEY")
    if not key:
        return None, False
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODEL}:generateContent",
            timeout=40, headers={"x-goog-api-key": key},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  # thinkingBudget=0 필수 — 안 주면 사고에 토큰을 다 쓰고
                  # 본문이 빈 채로 200 이 온다(예외도 안 난다).
                  "generationConfig": {"temperature": temperature,
                                       "maxOutputTokens": max_tokens,
                                       "thinkingConfig": {"thinkingBudget": 0}}})
        j = r.json()
        cands = j.get("candidates")
        if not cands:
            msg = json.dumps(j, ensure_ascii=False)[:140]
            _log(f"Gemini 무응답 (HTTP {r.status_code}): {msg}")
            return None, r.status_code == 429
        parts = cands[0].get("content", {}).get("parts") or []
        t = "".join(p.get("text", "") for p in parts).strip()
        return (t or None), False
    except Exception as e:
        _log(f"Gemini 호출 실패({type(e).__name__}: {str(e)[:70]})")
        return None, False


def ollama_available() -> bool:
    global _ollama_alive
    if _ollama_alive is None:
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
            names = [m.get("name", "") for m in r.json().get("models", [])]
            _ollama_alive = any(n.startswith(OLLAMA_MODEL.split(":")[0]) for n in names)
        except Exception:
            _ollama_alive = False
    return _ollama_alive


def _ollama(prompt: str, max_tokens: int, temperature: float) -> str | None:
    if not ollama_available():
        return None
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", timeout=300,
                          json={"model": OLLAMA_MODEL, "prompt": prompt,
                                "stream": False,
                                "options": {"temperature": temperature,
                                            "num_predict": max_tokens}})
        return (r.json().get("response") or "").strip() or None
    except Exception as e:
        _log(f"Ollama 실패({type(e).__name__}: {str(e)[:70]})")
        return None


def ask(prompt: str, *, max_tokens: int = 700, temperature: float = 0.8,
        retry_gemini: bool = True) -> str | None:
    """Gemini → (429면 재시도) → 로컬 Ollama 순으로 시도. 전부 실패하면 None."""
    out, retryable = _gemini(prompt, max_tokens, temperature)
    if out:
        return out

    # 무료키가 쿼터를 다 쓰면 **유료키로 넘어간다.** 무료키 하나를 AI뉴스·블로그·대본·
    # 사주가 공유하는 구조라, 남이 먼저 쓰면 내 차례에 429 가 난다(러너에서 실측).
    # flash 는 매우 저렴해서 하루 몇 건이면 비용이 사실상 무시된다.
    paid = os.environ.get("GEMINI_API_KEY_PAID")
    if retryable and paid and paid != os.environ.get("GEMINI_API_KEY"):
        out, _ = _gemini(prompt, max_tokens, temperature, key=paid)
        if out:
            _log("유료키로 처리(무료 쿼터 소진)")
            return out

    # 그래도 안 되면 잠깐 쉬고 재시도. 단 로컬이 살아 있으면 기다릴 이유가 없다.
    if retryable and retry_gemini and not ollama_available():
        time.sleep(35)
        out, _ = _gemini(prompt, max_tokens, temperature)
        if out:
            return out

    out = _ollama(prompt, max_tokens, temperature)
    if out:
        _log(f"로컬 폴백 사용({OLLAMA_MODEL})")
        return out
    return None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("ollama 가용:", ollama_available())
    print(ask("한 문장으로 인사해라.", max_tokens=100))
