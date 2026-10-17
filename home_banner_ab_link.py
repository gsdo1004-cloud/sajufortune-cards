# -*- coding: utf-8 -*-
"""Deterministic Threads link assignment for the sajufortune homepage OG-card A/B test.

Only text-only promotional posts should use this URL. Media posts and reply CTAs keep their
existing /links funnel because their uploaded media can hide the site's OG preview.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

EXPERIMENT = "home_og_hanbok_v1"
BASE = "https://sajufortune.kr"
CHANNEL_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,24}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PUBLICATION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


def publication_id(channel: str, date_iso: str) -> str:
    channel = str(channel or "").strip().lower()
    date_iso = str(date_iso or "").strip()
    if not CHANNEL_RE.fullmatch(channel) or not DATE_RE.fullmatch(date_iso):
        return ""
    return f"threads-{date_iso.replace('-', '')}-{channel}"


def variant_for(publication: str) -> str:
    publication = str(publication or "").strip()
    if not PUBLICATION_RE.fullmatch(publication):
        return ""
    digest = hashlib.sha256(f"{EXPERIMENT}|{publication}".encode("utf-8")).digest()
    return "B" if digest[0] & 1 else "A"


def publication_id_for_variant(
    channel: str, date_iso: str, target_variant: str, *, key: str = ""
) -> str:
    """Return a stable publisher-owned id whose server hash maps to target A/B.

    The server remains authoritative because the returned id is still checked by
    the same variant_for() contract.  A deterministic nonce is used only when the
    base id does not naturally land on the requested balanced variant.
    """
    base = publication_id(channel, date_iso)
    target = str(target_variant or "").strip().upper()
    key = str(key or "").strip()
    if not base or target not in {"A", "B"}:
        return ""
    if key and not KEY_RE.fullmatch(key):
        return ""
    stem = f"{base}-{key}" if key else base
    if len(stem) > 76:
        return ""
    for nonce in range(256):
        candidate = stem if nonce == 0 else f"{stem}-{nonce}"
        if len(candidate) > 80:
            break
        if variant_for(candidate) == target:
            return candidate
    return ""


def tracked_publication_url(publication: str, *, campaign: str, content: str = "") -> str:
    publication = str(publication or "").strip()
    variant = variant_for(publication)
    campaign = str(campaign or "").strip()[:100]
    content = str(content or "").strip()[:100]
    if not publication or not variant or not campaign:
        return ""
    params = {
        "utm_source": "threads",
        "utm_medium": "organic",
        "utm_campaign": campaign,
    }
    if content:
        params["utm_content"] = content
    return f"{BASE}/share/home-og/{publication}/{variant}?{urlencode(params)}"


def tracked_home_og_url(channel: str, date_iso: str) -> str:
    pub = publication_id(channel, date_iso)
    campaign = f"th_{date_iso.replace('-', '')}_{channel}"[:100]
    return tracked_publication_url(pub, campaign=campaign)


def register_publication_id(publication: str, *, status: str = "prepared",
                            platform_post_id: str = "", retries: int = 3) -> bool:
    """Prepare/finalize one publisher-owned A/B assignment on sajufortune.

    Fails closed: without the shared secret or after network/server failures the caller
    must keep using the legacy /links URL so no public post points at an unregistered share URL.
    """
    token = (os.environ.get("HOME_OG_AB_TOKEN") or "").strip()
    pub = str(publication or "").strip()
    variant = variant_for(pub)
    status = str(status or "").strip().lower()
    post_id = re.sub(r"[^A-Za-z0-9._-]", "", str(platform_post_id or ""))[:100]
    if not token or not pub or not variant or status not in {"prepared", "published"}:
        return False
    if status == "published" and not post_id:
        return False
    payload = json.dumps({
        "publication_id": pub,
        "variant": variant,
        "status": status,
        "platform_post_id": post_id,
    }, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/internal/home-og-ab/publication",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Home-Og-Ab-Token": token,
        },
        method="POST",
    )
    attempts = max(1, min(3, int(retries or 1)))
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                body = response.read(4096)
            doc = json.loads(body.decode("utf-8")) if body else {}
            return bool(doc.get("ok"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
    return False


def register_publication(channel: str, date_iso: str, *, status: str = "prepared",
                         platform_post_id: str = "", retries: int = 3) -> bool:
    """Backward-compatible wrapper for the existing ghost publisher."""
    return register_publication_id(
        publication_id(channel, date_iso),
        status=status,
        platform_post_id=platform_post_id,
        retries=retries,
    )
