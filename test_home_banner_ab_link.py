import datetime as dt
from urllib.parse import parse_qs, urlsplit

import threads_conversion as conv


def _ghost_conversion_date():
    d = dt.date(2026, 1, 1)
    for _ in range(370):
        iso = d.isoformat()
        if conv.stage("ghost", iso) == "conversion":
            return iso
        d += dt.timedelta(days=1)
    raise AssertionError("no deterministic ghost conversion day found")


def test_home_og_assignment_is_stable_and_matches_server_contract():
    from home_banner_ab_link import EXPERIMENT, publication_id, variant_for, tracked_home_og_url

    pub = publication_id("ghost", "2026-10-17")
    assert pub == "threads-20261017-ghost"
    v = variant_for(pub)
    assert v in {"A", "B"}
    assert variant_for(pub) == v
    url = tracked_home_og_url("ghost", "2026-10-17")
    parsed = urlsplit(url)
    assert parsed.path == f"/share/home-og/{pub}/{v}"
    q = parse_qs(parsed.query)
    assert q["utm_source"] == ["threads"]
    assert q["utm_medium"] == ["organic"]
    assert q["utm_campaign"] == [conv.campaign_key("ghost", "2026-10-17")]
    assert EXPERIMENT == "home_og_hanbok_v1"


def test_only_text_ghost_conversion_lane_uses_home_og_ab_link():
    date_iso = _ghost_conversion_date()
    ghost = conv.cta("ghost", date_iso, "쥐띠")
    assert "/share/home-og/threads-" in ghost
    assert "utm_source=threads" in ghost

    # Existing media/link and reply funnels remain on /links so this banner test
    # does not silently change their landing or pretend a hidden OG card was exposed.
    assert conv.tracked_url("signal", date_iso).startswith("https://sajufortune.kr/links?")
    assert conv.tracked_url("carousel", date_iso).startswith("https://sajufortune.kr/links?")
    assert conv.tracked_url("reply", date_iso).startswith("https://sajufortune.kr/links?")


def test_publisher_registration_sends_prepare_and_publish_receipt(monkeypatch):
    import json
    import home_banner_ab_link as ab

    sent = []

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, *args): return b'{"ok":true}'

    def fake_urlopen(req, timeout=0):
        sent.append((req, timeout))
        return _Resp()

    monkeypatch.setenv("HOME_OG_AB_TOKEN", "secret-test-token")
    monkeypatch.setattr(ab.urllib.request, "urlopen", fake_urlopen)
    assert ab.register_publication("ghost", "2026-10-17", status="prepared")
    assert ab.register_publication(
        "ghost", "2026-10-17", status="published", platform_post_id="thread-123"
    )
    assert len(sent) == 2
    prepare = json.loads(sent[0][0].data.decode("utf-8"))
    published = json.loads(sent[1][0].data.decode("utf-8"))
    assert prepare["status"] == "prepared" and not prepare["platform_post_id"]
    assert published["status"] == "published" and published["platform_post_id"] == "thread-123"
    assert sent[0][0].headers["X-home-og-ab-token"] == "secret-test-token"


def test_missing_registration_secret_fails_closed(monkeypatch):
    import home_banner_ab_link as ab
    monkeypatch.delenv("HOME_OG_AB_TOKEN", raising=False)
    assert not ab.register_publication("ghost", "2026-10-17", status="prepared")


def test_ghost_falls_back_to_legacy_link_if_prepare_receipt_fails(monkeypatch):
    import home_banner_ab_link as ab
    import zodiac_ghost as ghost

    date_iso = _ghost_conversion_date()
    original = ghost.build_text(date_iso)
    assert ab.tracked_home_og_url("ghost", date_iso) in original
    monkeypatch.setattr(ab, "register_publication", lambda *a, **k: False)
    prepared, active = ghost.prepare_home_og_publication(original, date_iso)
    assert not active
    assert ab.tracked_home_og_url("ghost", date_iso) not in prepared
    assert conv.tracked_url("ghost", date_iso) in prepared


def test_ghost_marks_published_after_successful_prepare(monkeypatch):
    import home_banner_ab_link as ab
    import zodiac_ghost as ghost

    date_iso = _ghost_conversion_date()
    original = ghost.build_text(date_iso)
    calls = []

    def fake_register(channel, date, *, status="prepared", platform_post_id=""):
        calls.append((channel, date, status, platform_post_id))
        return True

    monkeypatch.setattr(ab, "register_publication", fake_register)
    prepared, active = ghost.prepare_home_og_publication(original, date_iso)
    assert active and prepared == original
    assert ghost.finalize_home_og_publication(date_iso, "thread-999", active)
    assert calls == [
        ("ghost", date_iso, "prepared", ""),
        ("ghost", date_iso, "published", "thread-999"),
    ]


def test_ghost_workflow_code_push_cannot_publish_and_marker_precedes_receipt_sync():
    from pathlib import Path
    import zodiac_ghost as ghost

    workflow = (Path(__file__).parent / ".github" / "workflows" / "zodiac-ghost.yml").read_text(encoding="utf-8")
    on_block = workflow.split("jobs:", 1)[0]
    assert "  push:" not in on_block
    assert "schedule:" in on_block and "workflow_dispatch:" in on_block

    source = Path(ghost.__file__).read_text(encoding="utf-8")
    publish = source.index("pid = publish_ghost(text, date_iso)")
    marker_write = source.index("marker.write_text", publish)
    receipt = source.index("finalize_home_og_publication(date_iso, pid, True)", publish)
    assert publish < marker_write < receipt


def test_explicit_publication_variant_preserves_server_hash_contract():
    import home_banner_ab_link as ab

    fn = getattr(ab, "publication_id_for_variant", None)
    assert callable(fn), "publication_id_for_variant must exist for balanced publisher assignment"
    for target in ("A", "B"):
        pub = fn("ny2027", "2026-10-18", target, key="002")
        assert pub.startswith("threads-20261018-ny2027-002")
        assert len(pub) <= 80
        assert ab.variant_for(pub) == target


def test_explicit_publication_registration_uses_given_publication(monkeypatch):
    import json
    import home_banner_ab_link as ab

    fn = getattr(ab, "register_publication_id", None)
    assert callable(fn), "register_publication_id must exist for publisher-owned balanced ids"
    sent = []

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, *args): return b'{"ok":true}'

    def fake_urlopen(req, timeout=0):
        sent.append((req, timeout))
        return _Resp()

    monkeypatch.setenv("HOME_OG_AB_TOKEN", "secret-test-token")
    monkeypatch.setattr(ab.urllib.request, "urlopen", fake_urlopen)
    pub = ab.publication_id_for_variant("ny2027", "2026-10-18", "B", key="002")
    assert fn(pub, status="prepared")
    assert fn(pub, status="published", platform_post_id="thread-ny2027-2")
    payloads = [json.loads(x[0].data.decode("utf-8")) for x in sent]
    assert [p["publication_id"] for p in payloads] == [pub, pub]
    assert [p["variant"] for p in payloads] == ["B", "B"]
