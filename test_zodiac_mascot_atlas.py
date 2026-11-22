"""Offline deterministic 12-sign local FLUX portrait atlas without social publishing."""
import datetime as dt
import json
from pathlib import Path
import pytest
from PIL import Image, ImageDraw
from scripts.zodiac_character_prompts import NAMES
from scripts.zodiac_mascot_atlas import verify_atlas, compose_verified_day, AtlasHold
from scripts.visual_quality_gate import sha256
from scripts import flux_first_card_assets as fa
from scripts import zodiac_semantic_qa_gate as sem


def atlas_fixture(root,day="2026-11-24"):
    folder=root/"assets"/"zodiac_mascot_atlas"/"STYLE_02"
    folder.mkdir(parents=True)
    records=[]
    for i,name in enumerate(NAMES):
        color=(60+i*12,110+i*10,130+i*8)
        im=Image.new("RGB",(512,512),color)
        dr=ImageDraw.Draw(im)
        dr.ellipse((75,90,430,450),fill=(230-i*3,205+i*2,180+i*4))
        dr.ellipse((180,230,206,257),fill=(20,20,20))
        dr.ellipse((305,230,331,257),fill=(20,20,20))
        # Textured artificial fixtures exceed image-integrity byte threshold.
        im=Image.blend(im,Image.effect_noise((512,512),90).convert("RGB"),.07)
        path=folder/(name+".jpg")
        im.save(path,quality=90)
        records.append({"sign":name,"name":path.name,"sha256":sha256(path),
                        "provider":"flux2_klein_local","detected_species":name,
                        "subject_count":1,"cropped_face":False,"malformed_anatomy":False,
                        "text_artifacts":False,
                        "eastern_dragon_verified":True if name=="dragon" else None,
                        "friendly_non_scary":True if name in ("rat","snake") else None})
    m={"schema":"zodiac-verified-flux-atlas-v1","style_id":"STYLE_02",
       "status":"PASS","paid_api_calls":0,
       "verification_method":"independent_visual_review",
       "reviewer_reference":"SYNTHETIC_TEST_FIXTURE_NOT_A_REAL_REVIEW","files":records}
    (folder/"manifest.json").write_text(json.dumps(m,ensure_ascii=False),encoding="utf-8")
    return folder,m


def test_twelve_portraits_compose_six_correct_backgrounds(tmp_path):
    day="2026-11-24"
    atlas_fixture(tmp_path)
    assert len(verify_atlas(day,tmp_path)["files"])==12
    final=fa.prepare(day,tmp_path)  # automatic atlas path, no broker/API
    assert len(final["files"])==6
    assert final["mode"]=="VERIFIED_FLUX_ATLAS_COMPOSITE"
    assert final["paid_api_calls"]==0
    assert final["style_id"]=="STYLE_02"
    assert final["verified_atlas_manifest_sha256"]
    assert sem.verify_semantic(day,tmp_path,final)["status"]=="PASS"
    assert len(fa.verify(day,tmp_path)["files"])==6
    assert fa.prepare(day,tmp_path)==final  # no regeneration


def test_missing_portrait_or_bad_qa_holds(tmp_path):
    day="2026-11-24"
    folder,m=atlas_fixture(tmp_path)
    (folder/"rabbit.jpg").unlink()
    with pytest.raises(AtlasHold,match="ATLAS_SHA"):
        fa.prepare(day,tmp_path)
    assert not fa.folder(day,tmp_path).exists()


def test_bad_verified_species_identity_holds(tmp_path):
    day="2026-11-24"
    folder,m=atlas_fixture(tmp_path)
    m["files"][2]["detected_species"]="rabbit"
    (folder/"manifest.json").write_text(json.dumps(m),encoding="utf-8")
    with pytest.raises(AtlasHold,match="ATLAS_SINGLE_SPECIES_QA"):
        verify_atlas(day,tmp_path)


def test_atlas_revision_change_prevents_unchecked_semantic_pass(tmp_path):
    day="2026-11-24"
    folder,m=atlas_fixture(tmp_path)
    manifest=compose_verified_day(day,tmp_path)
    m["reviewer_reference"]="SYNTHETIC_TEST_FIXTURE_CHANGED"
    (folder/"manifest.json").write_text(json.dumps(m),encoding="utf-8")
    with pytest.raises(ValueError,match="ATLAS_MANIFEST_SHA_CHANGED"):
        sem.verify_semantic(day,tmp_path,manifest)


def test_generated_atlas_subject_prompt_is_one_animal_only(monkeypatch,tmp_path):
    from scripts import zodiac_mascot_atlas as atlas
    monkeypatch.setattr(fa,"_generate",lambda prompt,path,seed,**kwargs: _test_single_subject(prompt,path))
    result=atlas.generate_one_local("2026-11-24","dragon",tmp_path/"dragon.png")
    assert result["status"]=="UNVERIFIED_SOURCE"
    assert result["provider"]=="flux2_klein_local"
    assert "EXACTLY ONE" in result["prompt"] and "NO" in result["prompt"].upper()


def _test_single_subject(prompt,path):
    assert "EXACTLY ONE" in prompt
    Image.effect_noise((512,512),75).convert("RGB").save(path)
    return "flux2_klein_local"


def test_atlas_staging_resumes_and_never_self_certifies(monkeypatch,tmp_path):
    from scripts import zodiac_mascot_atlas as atlas
    monkeypatch.setattr(fa,"_generate",lambda prompt,path,seed,**kw: _test_single_subject(prompt,path))
    day="2026-11-24"
    a=atlas.stage_atlas_sources(day,tmp_path,max_new=2)
    assert a["total_staged"]==2 and a["remaining"]==10
    b=atlas.stage_atlas_sources(day,tmp_path,max_new=2)
    assert b["total_staged"]==4 and b["remaining"]==8
    manifest=json.loads((atlas.atlas_dir(day,tmp_path)/"manifest.json").read_text())
    assert manifest["status"]=="PENDING_QA"
    assert manifest["paid_api_calls"]==0
    with pytest.raises(AtlasHold,match="ATLAS_NOT_INDEPENDENTLY_VERIFIED"):
        atlas.verify_atlas(day,tmp_path)


def test_composite_atlas_flows_through_actual_card_renderer(tmp_path,monkeypatch):
    import zodiac_cardnews_tpl as renderer
    from scripts import zodiac_card_assets as cards
    day="2026-11-24"
    atlas_fixture(tmp_path)
    fa.prepare(day,tmp_path)
    monkeypatch.setattr(renderer,"BASE",tmp_path)
    monkeypatch.setattr(renderer,"FONT_DIR",Path(__file__).resolve().parent/"assets"/"fonts")
    monkeypatch.setattr(cards,"ROOT",tmp_path)
    output=cards.ensure(day)
    assert len(output)==6
    import json
    layout=json.loads((tmp_path/"cards"/day/"layout_manifest.json").read_text())
    assert all(r["status"]=="PASS" for r in layout["layout_reports"])
    assert all(image.exists() for image in output)
    assert cards.ensure(day)==output

def test_western_dragon_or_scary_rat_cannot_be_certified(tmp_path):
    folder,m=atlas_fixture(tmp_path)
    m["files"][4]["eastern_dragon_verified"]=False
    (folder/"manifest.json").write_text(json.dumps(m),encoding="utf-8")
    with pytest.raises(AtlasHold,match="ATLAS_SINGLE_SPECIES_QA"):
        verify_atlas("2026-11-24",tmp_path)
    m["files"][4]["eastern_dragon_verified"]=True
    m["files"][0]["friendly_non_scary"]=False
    (folder/"manifest.json").write_text(json.dumps(m),encoding="utf-8")
    with pytest.raises(AtlasHold,match="ATLAS_SINGLE_SPECIES_QA"):
        verify_atlas("2026-11-24",tmp_path)
