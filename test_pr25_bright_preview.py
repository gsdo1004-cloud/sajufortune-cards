from pathlib import Path
import pytest
from PIL import Image
from scripts import zodiac_bright_preview as b
from scripts.text_safe_layout_gate import LayoutHold

@pytest.mark.parametrize("key",["A","B"])
def test_palette_uses_actual_contrast_and_rejects_overlaps(key):
    c=b.Canvas(Image.new("RGB",(1080,1920),"white"),[],b.PALETTES[key])
    p=c.p
    c.panel((50,50,1030,220),p["blue"])
    c.text((540,80),"오늘의 운세",118,b.WHITE,p["blue"],center=True,area=(50,50,1030,220))
    assert c.finish()["actual_min_text_contrast"]>=4.5
    with pytest.raises(LayoutHold,match="OVERLAP"):
        c.text((540,80),"오늘의 운세",118,b.WHITE,p["blue"],center=True,area=(50,50,1030,220))
    with pytest.raises(LayoutHold,match="LOW_CONTRAST"):
        c.text((300,400),"날짜",50,"#FFFFFF","#FFFFDD")

def test_preview_rejects_source_directory_and_existing_output(tmp_path):
    source=tmp_path/"source";source.mkdir()
    existing=tmp_path/"A";existing.mkdir()
    for p in (source,source/"A",existing,tmp_path/"cards"):
        with pytest.raises(ValueError,match="fresh independent"):
            b.preview(source,"2026-12-07",p,"A")

def test_protected_region_unchanged():
    c=b.Canvas(Image.new("RGB",(1080,1920),"white"),[(100,100,300,300)],b.PALETTES["A"])
    c.panel((50,50,500,350))
    c.text((120,120),"띠",50,"#101828")
    with pytest.raises(LayoutHold,match="OVERLAP"):
        c.finish()

def test_four_primary_designs_rotate_independently_of_seven_styles():
    import datetime as dt
    from scripts.zodiac_style_rotation import style_for_day
    days=[(dt.date(2026,12,7)+dt.timedelta(days=i)).isoformat() for i in range(29)]
    designs=[b.design_for_day(d) for d in days]
    assert designs[0]=="PRIMARY_A"
    assert len(set(designs[:4]))==4
    assert all(a!=c for a,c in zip(designs,designs[1:]))
    assert len({(b.design_for_day(d),style_for_day(d)["id"]) for d in days[:28]})==28
    assert designs[28]==designs[0]

@pytest.mark.parametrize("design",list(b.DESIGNS))
def test_primary_design_text_contrast(design):
    from scripts.text_safe_layout_gate import contrast_ratio
    p={**b.PALETTES["A"],**b.DESIGNS[design]}
    for section in ("title","date","cta"):
        assert contrast_ratio(b.rgb(p[section+"_fg"]),b.rgb(p[section+"_bg"]))>=4.5
    assert p["bars"] and len(set(p["bars"]))==3

def test_production_build_refuses_existing_release_approval(tmp_path,monkeypatch):
    import zodiac_cardnews_tpl as t
    import json
    day="2026-12-07"
    monkeypatch.setattr(t,"BASE",tmp_path)
    src=tmp_path/"assets"/"flux_daily"/day;src.mkdir(parents=True)
    (src/"manifest.json").write_text(json.dumps({"style_id":"STYLE_01"}))
    approval=tmp_path/"assets"/"zodiac_release_approvals"/(day+".json")
    approval.parent.mkdir()
    approval.write_text("{}")
    with pytest.raises(LayoutHold,match="PUBLISHED_OR_APPROVED"):
        t.build(day)
