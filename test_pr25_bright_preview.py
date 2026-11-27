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
