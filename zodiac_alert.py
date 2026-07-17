# -*- coding: utf-8 -*-
"""띠별운세 파이프라인 실패 알림 — blog-auto의 실패메일 체계 재사용.

정본: D:\\blog_auto_work\\src\\email_publisher.py send_alert()
폴백: .env(NAVER_PW_gsd1004) 직접 파싱 + smtplib (rich 의존성 없이).
⚠️ local_hostname="localhost" 생략 금지 — 한글 호스트명 EHLO ascii 실패
   ([[feedback_korean_hostname_smtp_trap]]).
"""
from __future__ import annotations

import sys
from pathlib import Path

BLOG_AUTO = Path(r"D:\blog_auto_work")
TO = "gsdo1004@gmail.com"


def _env_naver_pw() -> str:
    env = BLOG_AUTO / ".env"
    if not env.exists():
        return ""
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith("NAVER_PW_gsd1004"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _fallback_mail(subject: str, body: str, to: str = TO) -> bool:
    import smtplib
    from email.mime.text import MIMEText
    pw = _env_naver_pw()
    if not pw:
        return False
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, "gsd1004@naver.com", to
    try:
        with smtplib.SMTP("smtp.naver.com", 587,
                          local_hostname="localhost", timeout=30) as s:
            s.starttls()
            s.login("gsd1004", pw)
            s.sendmail("gsd1004@naver.com", [to], msg.as_string())
        return True
    except Exception:
        return False


def alert(subject: str, body: str) -> bool:
    """실패 알림 메일. 성공 여부 반환(예외 없음)."""
    subject = f"[띠별운세] {subject}"
    try:
        sys.path.insert(0, str(BLOG_AUTO))
        from src.email_publisher import send_alert   # noqa
        if send_alert(subject, body, to=TO):
            return True
    except Exception:
        pass
    return _fallback_mail(subject, body)


if __name__ == "__main__":
    ok = alert("알림 경로 테스트", "띠별운세 파이프라인 알림 배선 테스트입니다.")
    print("메일 발송:", "OK" if ok else "FAIL")
