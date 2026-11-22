"""Deterministic twelve-sign composition from independently verified local FLUX portraits.

A 12-character prompt repeatedly produces duplicates. Once 12 original
FLUX-generated portraits per style have independent species QA, reuse them
indefinitely across daily cardnews/Shorts/Threads. No social or paid calls.
"""
from __future__ import annotations
import datetime as dt
import hashlib,json,os,shutil,tempfile
from pathlib import Path
from PIL import Image,ImageDraw,ImageFilter,ImageStat
from scripts.zodiac_style_rotation import style_for_day
from scripts.zodiac_character_prompts import TRAITS,NAMES,STEMS,SUBJECTS,protected_boxes
from scripts.visual_quality_gate import image_check,sha256

COLORS={
"STYLE_01":((255,243,236),(255,221,225)),
"STYLE_02":((251,242,225),(229,238,225)),
"STYLE_03":((250,240,230),(232,222,227)),
"STYLE_04":((237,241,255),(247,224,247)),
"STYLE_05":((255,240,222),(224,232,218)),
"STYLE_06":((244,231,213),(237,227,245)),
"STYLE_07":((240,242,255),(234,221,246)),
}

class AtlasHold(ValueError):pass

def atlas_dir(day: str,root: Path) -> Path:
    style=style_for_day(day)["id"]
    return Path(os.environ.get("SOCIAL_ZODIAC_ATLAS_ROOT",str(root/"assets"/"zodiac_mascot_atlas")))/style

def atlas_available(day: str,root: Path) -> bool:
    return (atlas_dir(day,root)/"manifest.json").exists()

def verify_atlas(day: str,root: Path) -> dict:
    folder=atlas_dir(day,root)
    path=folder/"manifest.json"
    try:
        manifest=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:raise AtlasHold("ATLAS_MANIFEST_UNAVAILABLE") from exc
    expected_style=style_for_day(day)["id"]
    if (manifest.get("schema")!="zodiac-verified-flux-atlas-v1" or
        manifest.get("style_id")!=expected_style or
        manifest.get("status")!="PASS" or manifest.get("paid_api_calls")!=0 or
        manifest.get("verification_method") not in ("local_vision_model","independent_visual_review") or
        not manifest.get("reviewer_reference")):
        raise AtlasHold("ATLAS_NOT_INDEPENDENTLY_VERIFIED")
    records=manifest.get("files") or []
    if len(records)!=12 or [v.get("sign") for v in records]!=list(NAMES):
        raise AtlasHold("ATLAS_SPECIES_INCOMPLETE_OR_DUPLICATE")
    for record in records:
        name=record["sign"]
        filename=name+".jpg"
        image=folder/filename
        if (record.get("name")!=filename or record.get("provider")!="flux2_klein_local"
            or record.get("detected_species")!=name or record.get("subject_count")!=1
            or record.get("cropped_face") is not False or record.get("malformed_anatomy") is not False
            or record.get("text_artifacts") is not False
            or (name=="dragon" and record.get("eastern_dragon_verified") is not True)
            or (name in ("rat","snake") and record.get("friendly_non_scary") is not True)):
            raise AtlasHold("ATLAS_SINGLE_SPECIES_QA_FAIL_"+name)
        if not image.is_file() or sha256(image)!=record.get("sha256"):
            raise AtlasHold("ATLAS_SHA_MISMATCH_"+name)
        image_check(image,size=(512,512),min_bytes=8000)
    return manifest

def _gradient(w,h,top,bottom):
    # Deterministic gentle picturebook background, no text pixels.
    im=Image.new("RGB",(w,h))
    dr=ImageDraw.Draw(im)
    for y in range(h):
        t=y/max(h-1,1)
        color=tuple(round((1-t)*a+t*b) for a,b in zip(top,bottom))
        dr.line((0,y,w,y),fill=color)
    return im

def _paste_portrait(canvas,avatar_path,box):
    x1,y1,x2,y2=box
    border=Image.new("RGBA",(x2-x1,y2-y1),(255,255,255,0))
    overlay=Image.new("RGBA",border.size,(0,0,0,0))
    panel=ImageDraw.Draw(overlay)
    panel.rounded_rectangle((3,3,border.width-4,border.height-4),
                            radius=min(28,border.width//7),fill=(255,255,255,230))
    border.alpha_composite(overlay)
    with Image.open(avatar_path) as src:
        portrait=src.convert("RGBA")
        side=min(border.width-28,border.height-28)
        portrait=portrait.resize((side,side),Image.Resampling.LANCZOS)
    x=(border.width-side)//2;y=(border.height-side)//2
    border.alpha_composite(portrait,(x,y))
    canvas.paste(border,(x1,y1),border)

def layout_regions(stem: str) -> list[dict]:
    # Whole portrait tiles are used as conservative protected animal zones.
    if stem=="01_표지":
        return [{"sign":name,"bbox":[65+(i%4)*240,450+(i//4)*365,
                                      65+(i%4)*240+220,450+(i//4)*365+315]}
                for i,name in enumerate(NAMES)]
    if stem=="06_12띠요약":
        return [{"sign":name,"bbox":[25+i*86,1748,25+i*86+70,1830]}
                for i,name in enumerate(NAMES)]
    idx=STEMS.index(stem)
    return [{"sign":name,"bbox":[28,220+j*490,296,220+j*490+395]}
            for j,name in enumerate(SUBJECTS[idx])]


def _compose(day: str,stem: str,atlas_folder:Path):
    style=style_for_day(day)["id"]
    top,bottom=COLORS[style]
    image=_gradient(1080,1920,top,bottom)
    dr=ImageDraw.Draw(image)
    dr.rounded_rectangle((20,18,1060,1902),radius=58,outline=(185,169,149),width=7)
    dr.ellipse((26,1650,168,1792),outline=(218,181,145),width=8)
    dr.ellipse((916,110,1054,246),outline=(218,181,145),width=8)
    for region in layout_regions(stem):
        _paste_portrait(image,atlas_folder/(region["sign"]+".jpg"),tuple(region["bbox"]))
    return image

def compose_verified_day(day: str,root:Path):
    """Six-card output is atomic; never overwrite assets or published days."""
    from scripts import flux_first_card_assets as fa
    atlas=verify_atlas(day,root)
    folder=atlas_dir(day,root)
    target=fa.folder(day,root)
    if target.exists():
        return fa.verify(day,root)
    receipts=("threads_pub_*.json","instagram_pub_*.json","youtube_pub*.json","uploaded.json")
    card_folder=root/"cards"/day
    if any(any(card_folder.glob(pat)) for pat in receipts):
        raise AtlasHold("PUBLISHED_DAY_PROTECTED")
    target.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix=".zodiac-atlas-staging-",dir=target.parent))
    style=style_for_day(day)
    try:
        entries=[]
        for i,stem in enumerate(STEMS):
            image=_compose(day,stem,folder)
            out=staging/(stem+".jpg")
            image.save(out,"JPEG",quality=90,optimize=True)
            image_check(out,size=(1080,1920),min_bytes=50000)
            seed=int(day.replace("-",""))*10+i+1
            entries.append({"name":out.name,"sha256":sha256(out),"provider":"flux2_klein_local",
                            "style_id":style["id"],"style_name":style["name"],
                            "subject":"east_asian_zodiac","main_zodiac":list(SUBJECTS[i]),
                            "protected_regions":[list(box) for box in protected_boxes(stem,1080,1920)],
                            "prompt":"deterministic composite of reviewed single-zodiac FLUX portraits",
                            "seed":seed,"safe_top_ratio":.22,"safe_bottom_ratio":.14,
                            "image_provider":"flux2_klein_local","model":"flux2_klein_local",
                            "verified_atlas_manifest_sha256":sha256(folder/"manifest.json"),
                            "face_boxes":layout_regions(stem),
                            "face_box_provenance":"verified_single_portraits_fixed_tile_geometry"})
        m={"schema":fa.SCHEMA,"date":day,"mode":"VERIFIED_FLUX_ATLAS_COMPOSITE",
           "style_id":style["id"],"style_name":style["name"],"subject":"east_asian_zodiac",
           "layout_protection_source":"verified_atlas_and_deterministic_composition",
           "verified_atlas_manifest_sha256":sha256(folder/"manifest.json"),
           "allow_paid":False,"max_paid_provider_attempts":0,"paid_api_calls":0,"files":entries}
        (staging/"manifest.json").write_text(json.dumps(m,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        if target.exists():raise AtlasHold("CONCURRENT_DAY_INVENTORY")
        staging.rename(target)
        try:return fa.verify(day,root)
        except Exception:
            target.rename(staging);raise
    finally:
        if staging.exists():shutil.rmtree(staging)

def generate_one_local(day: str,sign:str,path:Path):
    """Acquisition helper, never auto-certifies a portrait as correct."""
    from scripts.flux_first_card_assets import _generate
    if sign not in TRAITS:raise ValueError("unknown zodiac")
    style=style_for_day(day)
    prompt=(f"EXACTLY ONE original baby Korean zodiac mascot: {TRAITS[sign]}. "
            f"ONLY ONE animal, no other animals. {style['name']}: {style['prompt']}. "
            "Full body and entire face in a centered square composition, "
            "clean pale warm backdrop, no writing, no logos, no cropped ears or limbs.")
    # Square local FLUX canvas avoids stretching/cropping portrait mascots.
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=path.with_suffix(".source.png")
    try:
        provider=_generate(prompt,raw,int(day.replace("-",""))*100+list(NAMES).index(sign),
                           width=768,height=768)
        if provider!="flux2_klein_local":raise AtlasHold("NOT_VERIFIED_LOCAL_FLUX")
        with Image.open(raw) as im:
            color=im.convert("RGB").resize((512,512),Image.Resampling.LANCZOS)
            color.save(path,"JPEG",quality=92,optimize=True)
        image_check(path,size=(512,512),min_bytes=8000)
    finally:
        raw.unlink(missing_ok=True)
    return {"provider":provider,"prompt":prompt,"status":"UNVERIFIED_SOURCE",
            "sha256":sha256(path),"seed":int(day.replace("-",""))*100+list(NAMES).index(sign)}


def stage_atlas_sources(day: str,root:Path,max_new:int=12) -> dict:
    """Precompute new portraits sequentially; NEVER marks them as audited."""
    if not 1<=max_new<=12:raise ValueError("max_new must be 1..12")
    folder=atlas_dir(day,root)
    prior_path=folder/"manifest.json"
    if prior_path.exists():
        existing=json.loads(prior_path.read_text(encoding="utf-8"))
        if existing.get("status")=="PASS":
            return verify_atlas(day,root)
        if existing.get("status")!="PENDING_QA":
            raise AtlasHold("UNRECOGNIZED_ATLAS_STATE")
    else:
        existing={"schema":"zodiac-verified-flux-atlas-v1",
                  "style_id":style_for_day(day)["id"],"status":"PENDING_QA",
                  "paid_api_calls":0,"verification_method":None,
                  "reviewer_reference":None,"files":[]}
    folder.mkdir(parents=True,exist_ok=True)
    original={record["sign"]:record for record in existing["files"]}
    new_count=0
    for name in NAMES:
        source=folder/(name+".jpg")
        previous=original.get(name)
        if (previous and source.is_file() and previous.get("sha256")==sha256(source)
                and previous.get("provider")=="flux2_klein_local"):
            continue
        if new_count>=max_new:break
        detail=generate_one_local(day,name,source)
        original[name]={"sign":name,"name":source.name,"sha256":detail["sha256"],
                        "provider":"flux2_klein_local","seed":detail["seed"],
                        "prompt":detail["prompt"],"status":"PENDING_QA",
                        "detected_species":None,"subject_count":None,
                        "cropped_face":None,"malformed_anatomy":None,
                        "text_artifacts":None}
        new_count+=1
        existing["files"]=[original[n] for n in NAMES if n in original]
        # Atomic progress marker: interrupted runs resume with validated hashes.
        temp=folder/"manifest.json.tmp"
        temp.write_text(json.dumps(existing,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        temp.replace(prior_path)
    return {"status":"PENDING_QA","style_id":style_for_day(day)["id"],
            "generated_this_run":new_count,"total_staged":len(original),
            "remaining":12-len(original),"paid_api_calls":0}

