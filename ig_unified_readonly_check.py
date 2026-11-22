# -*- coding: utf-8 -*-
"""Non-publishing, non-logging Instagram Unified Login API smoke test.
Uses only a GitHub Actions secret, never prints tokens, URLs, response bodies,
identifiers or private account data. Separate from existing Instagram pipeline.
"""
import json
import os
import urllib.error
import urllib.request

TOKEN = os.environ.get("INSTAGRAM_UNIFIED_ACCESS_TOKEN", "").strip()
EXPECTED_ID = "17841448828636115"
EXPECTED_USERNAME = "gsdo10042026"
BASE = "https://graph.facebook.com/v27.0"


def graph_get(path):
    request = urllib.request.Request(
        BASE + "/" + path,
        headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as exc:
        # API error messages, response bodies and request URLs must never be logged.
        try:
            obj = json.load(exc)
            err = obj.get("error", {}) if isinstance(obj, dict) else {}
            code = err.get("code")
            sub = err.get("error_subcode")
        except Exception:
            code, sub = None, None
        print(json.dumps({"check": "http", "status": "FAIL",
                          "http_status": exc.code, "api_code": code,
                          "api_subcode": sub}, ensure_ascii=False))
        raise SystemExit(1) from None
    except Exception:
        print('{"check":"network","status":"FAIL"}')
        raise SystemExit(1) from None


def main():
    if not TOKEN:
        print('{"check":"secret_present","status":"FAIL"}')
        return 1
    print('{"check":"secret_present","status":"OK"}')
    status, profile = graph_get(EXPECTED_ID + "?fields=id,username")
    if (status != 200 or not isinstance(profile, dict)
            or str(profile.get("id")) != EXPECTED_ID
            or str(profile.get("username", "")).casefold() != EXPECTED_USERNAME):
        print('{"check":"account_identity","status":"FAIL"}')
        return 1
    print('{"check":"account_identity","status":"OK"}')
    status, media = graph_get(EXPECTED_ID + "/media?fields=id&limit=1")
    if status != 200 or not isinstance(media, dict) or not isinstance(media.get("data"), list):
        print('{"check":"media_read","status":"FAIL"}')
        return 1
    print('{"check":"media_read","status":"OK"}')
    print('{"check":"ig_unified_readonly","status":"SUCCESS","external_writes":0}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
