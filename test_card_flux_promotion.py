import hashlib
import json
import sys
import types
from pathlib import Path

import pytest
from PIL import Image
from scripts import zodiac_card_assets as a
from scripts import flux_first_card_assets as fa


def make_cards(root,day):
    folder=root/"cards"/day
    folder.mkdir(parents=True,exist_ok=True)
    for i in range(1,7):
        img=Image.effect_noise((1080,1920),i*17).convert("RGB")
        img.save(folder/f"card_{i:02}.jpg",quality=85)
    return folder


def manifest(root,day):
    p=root/"assets"/"flux_daily"/day/"manifest.json"
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text('{"test":"verified-by-mock"}')
    return p


def test_promote_only_unpublished_cards(monkeypatch,tmp_path):
    day="2026-11-24"
    folder=make_cards(tmp_path,day)
    old=a.verify(day,tmp_path)
    old_hash=hashlib.sha256(old[0].read_bytes()).hexdigest()
    m=manifest(tmp_path,day)
    monkeypatch.setattr(a,"ROOT",tmp_path)
    monkeypatch.setattr(fa,"verify",lambda day,root:{"ok":True})
    calls=[]
    def build(day):
        calls.append(day)
        Image.effect_noise((1080,1920),130).convert("RGB").save(folder/"card_01.jpg",quality=85)
    monkeypatch.setitem(sys.modules,"zodiac_cardnews_tpl",types.SimpleNamespace(build=build))
    assert len(a.ensure(day))==6
    assert calls==[day]
    assert hashlib.sha256((folder/"card_01.jpg").read_bytes()).hexdigest()!=old_hash
    marker=json.loads((folder/"flux_backgrounds_applied.json").read_text())
    assert marker["flux_manifest_sha256"]==hashlib.sha256(m.read_bytes()).hexdigest()
    a.ensure(day)
    assert calls==[day]  # no repeated rewriting


def test_published_day_cannot_be_replaced(monkeypatch,tmp_path):
    day="2026-11-24"
    folder=make_cards(tmp_path,day)
    (folder/"threads_pub_carousel.json").write_text('{"post_id":"abc"}')
    manifest(tmp_path,day)
    monkeypatch.setattr(a,"ROOT",tmp_path)
    monkeypatch.setattr(fa,"verify",lambda day,root:{"ok":True})
    monkeypatch.setitem(sys.modules,"zodiac_cardnews_tpl",types.SimpleNamespace(build=lambda *_:pytest.fail("published rewrite")))
    assert len(a.ensure(day))==6
    assert not (folder/"flux_backgrounds_applied.json").exists()


def test_partial_card_render_failure_restores_exact_bytes(monkeypatch,tmp_path):
    day="2026-11-25"
    folder=make_cards(tmp_path,day)
    prior={f.name:f.read_bytes() for f in folder.glob("card_*.jpg")}
    manifest(tmp_path,day)
    monkeypatch.setattr(a,"ROOT",tmp_path)
    monkeypatch.setattr(fa,"verify",lambda day,root:{"ok":True})
    def bad_build(day):
        (folder/"card_01.jpg").write_bytes(b"half-written")
        raise RuntimeError("render failed")
    monkeypatch.setitem(sys.modules,"zodiac_cardnews_tpl",types.SimpleNamespace(build=bad_build))
    with pytest.raises(RuntimeError,match="render failed"):
        a.ensure(day)
    assert {f.name:f.read_bytes() for f in folder.glob("card_*.jpg")}==prior
    assert not (folder/"flux_backgrounds_applied.json").exists()


def test_invalid_flux_bundle_never_replaces_cards(monkeypatch,tmp_path):
    day="2026-11-26"
    folder=make_cards(tmp_path,day)
    prior={f.name:f.read_bytes() for f in folder.glob("card_*.jpg")}
    manifest(tmp_path,day)
    monkeypatch.setattr(a,"ROOT",tmp_path)
    monkeypatch.setattr(fa,"verify",lambda day,root:(_ for _ in ()).throw(ValueError("bad hash")))
    with pytest.raises(ValueError,match="bad hash"):
        a.ensure(day)
    assert {f.name:f.read_bytes() for f in folder.glob("card_*.jpg")}==prior
