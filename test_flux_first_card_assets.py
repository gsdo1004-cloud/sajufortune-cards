import json
from pathlib import Path
import pytest
from PIL import Image, ImageStat
from scripts import flux_first_card_assets as fa


def test_flux_first_complete_and_corruption_holds(tmp_path):
    day="2026-11-24"
    calls=[]
    def no_paid_mock(prompt,path,seed):
        calls.append(seed)
        assert "text" in prompt or "no text" in prompt
        im=Image.effect_noise((512,896),72).convert("RGB")
        im.save(path)
        return "flux2_klein_local"
    result=fa.prepare(day,tmp_path,generator=no_paid_mock)
    assert len(result["files"])==6
    assert result["paid_api_calls"]==0
    assert len(calls)==6
    for stem in fa.STEMS:
        assert fa.background_path_for(day,stem,tmp_path).is_file()
    assert fa.prepare(day,tmp_path,generator=lambda *a: pytest.fail("must not regenerate"))==result
    item=fa.folder(day,tmp_path) / (fa.STEMS[0]+".jpg")
    with item.open("ab") as f:f.write(b"tampered")
    with pytest.raises(ValueError,match="hash mismatch"):
        fa.verify(day,tmp_path)


def test_missing_bank_fallback_and_partial_flux_hold(tmp_path):
    day="2026-11-25"
    assert fa.background_path_for(day,"01_표지",tmp_path) is None
    fa.folder(day,tmp_path).mkdir(parents=True)
    with pytest.raises((ValueError,FileNotFoundError)):
        fa.background_path_for(day,"01_표지",tmp_path)


def test_never_replace_published_day(tmp_path):
    day="2026-11-26"
    receipt=tmp_path/"cards"/day/"threads_pub_carousel.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"post_id":"one"}')
    with pytest.raises(ValueError,match="published"):
        fa.prepare(day,tmp_path,generator=lambda *args: pytest.fail("no generation"))
