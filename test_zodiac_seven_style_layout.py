"""Offline seven-style, original-zodiac, actual text geometry, safety and video QA."""
import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageFont
from scripts.zodiac_style_rotation import style_for_day, week_ids
from scripts.zodiac_character_prompts import TRAITS, STEMS, SUBJECTS, prompt_for, protected_boxes
from scripts.text_safe_layout_gate import TrackedDraw, check_layout, intersects, LayoutHold
from scripts.visual_quality_gate import image_check, video_check, VisualHold
from scripts import flux_first_card_assets as fa


@pytest.mark.parametrize("n", range(7))
def test_seven_real_prompt_variations(n):
    day=(dt.date(2026,11,23)+dt.timedelta(days=n)).isoformat()
    style=style_for_day(day)
    assert style["id"]==f"STYLE_{n+1:02d}"
    p=prompt_for(day,"01_표지")
    assert style["id"] in p and "EXACTLY 12" in p and "NO wings" in p
    assert all(name in p for name in TRAITS)


def test_seven_styles_have_unique_ids_and_prompts():
    assert len(set(week_ids("2026-11-22")))==7
    assert len(TRAITS)==12 and len(STEMS)==6
    assert "East Asian" in TRAITS["dragon"] and "NO wings" in TRAITS["dragon"]
    assert "adorable" in TRAITS["snake"] and "friendly" in TRAITS["rat"]


def test_measured_text_versus_protected_regions():
    subject=(150,450,970,1475)
    assert intersects(subject,(200,500,420,600))
    fail=check_layout([(200,500,420,600)], [subject],1080,1920)
    assert fail["status"]=="HOLD"
    assert any(x.startswith("TEXT_SUBJECT_OVERLAP") for x in fail["reason_codes"])
    ok=check_layout([(90,190,950,290)], [subject],1080,1920)
    assert ok["status"]=="PASS" and ok["contrast_ratio"]>=4.5
    outside=check_layout([(-3,20,200,90)], [],1080,1920)
    assert "TEXT_OUTSIDE_0" in outside["reason_codes"]


def test_actual_draw_records_and_automatically_moves_text():
    im=Image.new("RGB",(1080,1920),"white")
    dr=TrackedDraw(im,[(100,100,350,400)])
    dr.text((180,150),"SAFE",font=ImageFont.load_default(),fill=(20,20,30))
    report=dr.verify()
    assert report["status"]=="PASS"
    assert len(report["measured_text_boxes"])==1
    assert report["auto_fixes"]


def test_unfixable_text_holds():
    im=Image.new("RGB",(150,200),"white")
    dr=TrackedDraw(im,[(0,0,150,200)])
    with pytest.raises(LayoutHold):
        dr.text((20,20),"blocked",font=ImageFont.load_default(),fill=(0,0,0))


def test_style_manifest_hash_and_fallback_are_no_paid(tmp_path):
    day="2026-11-24"
    def included_only(prompt,out,seed):
        assert "STYLE_02" in prompt and "text" in prompt
        Image.effect_noise((512,896),72).convert("RGB").save(out)
        return "gemini_subscription_included_if_available"
    m=fa.prepare(day,tmp_path,generator=included_only)
    assert m["style_id"]=="STYLE_02"
    assert m["paid_api_calls"]==0 and m["allow_paid"] is False
    assert m["max_paid_provider_attempts"]==0
    assert all(f["style_id"]=="STYLE_02" and f["prompt"] and f["seed"] for f in m["files"])
    assert all(f["provider"]=="gemini_subscription_included_if_available" for f in m["files"])
    assert all(f["protected_regions"]==[list(x) for x in protected_boxes(stem,1080,1920)]
               for stem,f in zip(STEMS,m["files"]))
    assert len(fa.verify(day,tmp_path)["files"])==6
    assert image_check(fa.folder(day,tmp_path)/(STEMS[0]+".jpg"))["status"]=="PASS"


def test_published_receipt_prevents_rerender_on_other_social_platforms(tmp_path):
    day="2026-11-26"
    d=tmp_path/"cards"/day
    d.mkdir(parents=True)
    (d/"instagram_pub_reels.json").write_text('{"id":"do-not-duplicate"}')
    with pytest.raises(ValueError,match="published"):
        fa.prepare(day,tmp_path,generator=lambda *a:pytest.fail("MUST NOT generate"))


def test_blank_and_broken_image_hold(tmp_path):
    broken=tmp_path/"broken.jpg"
    broken.write_bytes(b"not a JPEG"+b"x"*100000)
    with pytest.raises(VisualHold):
        image_check(broken)
    black=tmp_path/"black.jpg"
    Image.new("RGB",(1080,1920),"black").save(black,quality=96)
    with pytest.raises(VisualHold):
        image_check(black,min_bytes=1000)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="ffmpeg required")
def test_real_mp4_probe_and_three_frames(tmp_path):
    video=tmp_path/"original.mp4"
    subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-f","lavfi",
                    "-i","testsrc2=size=1080x1920:rate=3:duration=2",
                    "-c:v","libx264","-preset","ultrafast","-crf","30",
                    "-pix_fmt","yuv420p",str(video)],check=True,timeout=70)
    report=video_check(video,min_bytes=2000)
    assert report["status"]=="PASS" and report["codec"]=="h264"
    assert len(report["sample_frames"])==3


def test_legacy_manifest_style_does_not_masquerade_as_seven_style(tmp_path,monkeypatch):
    import zodiac_cardnews_tpl as tpl
    day="2026-11-23"
    target=tmp_path/"assets"/"flux_daily"/day
    target.mkdir(parents=True)
    (target/"manifest.json").write_text(json.dumps({"schema":"social-flux-backgrounds-v1","date":day,
                                                    "files":[],"paid_api_calls":0}))
    monkeypatch.setattr(tpl,"BASE",tmp_path)
    assert tpl._flux_active(day) is False


def test_full_six_card_render_measures_actual_text_and_saves_gate(tmp_path,monkeypatch):
    """Synthetic backgrounds exercise the production PIL renderer; not FLUX image QA."""
    import zodiac_cardnews_tpl as tpl
    from scripts import zodiac_card_assets as cards
    day="2026-11-24"
    def mock_generator(prompt,path,seed):
        Image.effect_noise((512,896),66).convert("RGB").save(path)
        return "flux2_klein_local"
    fa.prepare(day,tmp_path,generator=mock_generator)
    # Synthetic fixture tests layout only; never claim animal semantic review.
    from scripts import zodiac_semantic_qa_gate as semantic
    monkeypatch.setattr(semantic,"verify_semantic",lambda *args:{"status":"TEST_FIXTURE_ONLY"})
    font_directory=Path(__file__).resolve().parent/"assets"/"fonts"
    monkeypatch.setattr(tpl,"BASE",tmp_path)
    monkeypatch.setattr(tpl,"FONT_DIR",font_directory)
    monkeypatch.setattr(cards,"ROOT",tmp_path)
    six=tpl.build(day)
    assert len(six)==6
    assert len(cards.verify(day,tmp_path))==6
    report=json.loads((tmp_path/"cards"/day/"layout_manifest.json").read_text())
    assert len(report["layout_reports"])==6
    assert all(r["status"]=="PASS" and r["measured_text_boxes"]
               for r in report["layout_reports"])
    assert all(not r["reason_codes"] for r in report["layout_reports"])


def test_preview_suite_holds_when_authentic_styles_are_missing(tmp_path):
    from scripts.zodiac_preview_suite import render
    result=render(tmp_path/"sources",tmp_path/"review",Path(__file__).resolve().parent)
    assert result["status"]=="HOLD"
    assert result["count"]==0
    assert len(result["missing_real_flux_styles"])==7


def test_new_style_bundle_promotes_only_before_publication(tmp_path,monkeypatch):
    """Exercises original ensure -> full PIL render -> manifest -> verify chain."""
    import zodiac_cardnews_tpl as tpl
    from scripts import zodiac_card_assets as cards
    day="2026-11-24"
    def mock_generator(prompt,path,seed):
        Image.effect_noise((512,896),73).convert("RGB").save(path)
        return "flux2_klein_local"
    fa.prepare(day,tmp_path,generator=mock_generator)
    # Synthetic fixture tests layout only; never claim animal semantic review.
    from scripts import zodiac_semantic_qa_gate as semantic
    monkeypatch.setattr(semantic,"verify_semantic",lambda *args:{"status":"TEST_FIXTURE_ONLY"})
    monkeypatch.setattr(tpl,"BASE",tmp_path)
    monkeypatch.setattr(tpl,"FONT_DIR",Path(__file__).resolve().parent/"assets"/"fonts")
    monkeypatch.setattr(cards,"ROOT",tmp_path)
    first=cards.ensure(day)
    assert len(first)==6
    marker=tmp_path/"cards"/day/"flux_backgrounds_applied.json"
    assert json.loads(marker.read_text())["status"]=="APPLIED"
    hashes=[p.read_bytes() for p in first]
    second=cards.ensure(day)
    assert [p.read_bytes() for p in second]==hashes
    (tmp_path/"cards"/day/"threads_pub_carousel.json").write_text('{"id":"published"}')
    assert [p.read_bytes() for p in cards.ensure(day)]==hashes

def test_real_flux_bundle_cannot_promote_without_independent_species_qa(tmp_path,monkeypatch):
    from scripts import zodiac_card_assets as cards
    day="2026-11-24"
    def fake_image(prompt,path,seed):
        Image.effect_noise((512,896),70).convert("RGB").save(path)
        return "flux2_klein_local"
    fa.prepare(day,tmp_path,generator=fake_image)
    monkeypatch.setattr(cards,"ROOT",tmp_path)
    with pytest.raises(ValueError,match="SEMANTIC_QA_MISSING"):
        cards.ensure(day)
    assert not (tmp_path/"cards"/day/"flux_backgrounds_applied.json").exists()


def test_false_species_count_receipt_fails(tmp_path):
    from scripts.zodiac_semantic_qa_gate import verify_semantic, audit_path, SemanticHold
    day="2026-11-24"
    def fake_image(prompt,path,seed):
        Image.effect_noise((512,896),70).convert("RGB").save(path)
        return "flux2_klein_local"
    manifest=fa.prepare(day,tmp_path,generator=fake_image)
    reviews=[{"name":i["name"],"sha256":i["sha256"],"status":"PASS",
              "species":["rat"],"duplicate_species_count":0,
              "cropped_faces":False,"malformed_anatomy":False,
              "text_artifacts":False,
              "faces":[{"sign":name,"bbox":[30+j*60,450,80+j*60,525]}
                       for j,name in enumerate(SUBJECTS[index])]}
             for index,i in enumerate(manifest["files"])]
    receipt={"schema":"zodiac-semantic-qa-v1","date":day,
             "style_id":"STYLE_02","verification_method":"independent_visual_review",
             "reviewer_reference":"test-fixture-no-real-review","status":"PASS","images":reviews}
    path=audit_path(day,tmp_path);path.parent.mkdir(parents=True)
    path.write_text(json.dumps(receipt),encoding="utf-8")
    with pytest.raises(SemanticHold,match="SEMANTIC_QA_IMAGE_FAIL"):
        verify_semantic(day,tmp_path,manifest)


def test_visual_underlay_heuristic_rejects_busy_image_beneath_text():
    from scripts.visual_quality_gate import underlay_detail_check
    image=Image.new("RGB",(1080,1920),(249,243,238))
    image.paste(Image.effect_noise((540,260),70).convert("RGB"),(270,160))
    bad=underlay_detail_check(image,[(270,160,810,420)],threshold=.049)
    assert bad["status"]=="HOLD"
    good=underlay_detail_check(image,[(270,1430,810,1550)],threshold=.049)
    assert good["status"]=="PASS"
    assert good["method"]=="heuristic_edge_density_not_face_detection"


def test_review_only_21_preview_sheet_never_claims_semantic_approval(tmp_path):
    from scripts.zodiac_preview_suite import render
    from scripts.zodiac_style_rotation import STYLES
    import hashlib
    sources=tmp_path/"sources";sources.mkdir()
    for ident,_,_ in STYLES:
        image=sources/(ident+"_cover.png")
        synthetic=Image.effect_noise((768,1344),72).convert("RGB")
        synthetic.save(image,"PNG")
        receipt={"style_id":ident,"provider":"flux2_klein_local",
                 "sha256":hashlib.sha256(image.read_bytes()).hexdigest(),
                 "paid_api_calls":0}
        (sources/(ident+"_receipt.json")).write_text(json.dumps(receipt))
    result=render(sources,tmp_path/"review",Path(__file__).resolve().parent,video=False)
    assert result["count"]==21
    assert result["status"]=="REVIEW_REQUIRED"
    assert result["semantic_qa"]=="NOT_AUTOMATICALLY_VERIFIED"
    assert (tmp_path/"review"/"zodiac_21_previews.jpg").is_file()
    assert all(Path(x["image"]).exists() for x in result["samples"])
    assert result["paid_api_calls"]==0 and result["publication_attempts"]==0

def test_missing_independent_face_boxes_holds(tmp_path):
    from scripts.zodiac_semantic_qa_gate import verify_semantic, audit_path, SemanticHold
    day="2026-11-24"
    def fake_image(prompt,path,seed):
        Image.effect_noise((512,896),70).convert("RGB").save(path)
        return "flux2_klein_local"
    manifest=fa.prepare(day,tmp_path,generator=fake_image)
    reviews=[{"name":i["name"],"sha256":i["sha256"],"status":"PASS",
              "species":list(SUBJECTS[index]),"duplicate_species_count":0,
              "cropped_faces":False,"malformed_anatomy":False,
              "text_artifacts":False,"faces":[]}
             for index,i in enumerate(manifest["files"])]
    receipt={"schema":"zodiac-semantic-qa-v1","date":day,"style_id":"STYLE_02",
             "verification_method":"independent_visual_review",
             "reviewer_reference":"SYNTHETIC_TEST_ONLY","status":"PASS","images":reviews}
    p=audit_path(day,tmp_path);p.parent.mkdir(parents=True);p.write_text(json.dumps(receipt))
    with pytest.raises(SemanticHold,match="SEMANTIC_FACE_BOXES_MISSING"):
        verify_semantic(day,tmp_path,manifest)
