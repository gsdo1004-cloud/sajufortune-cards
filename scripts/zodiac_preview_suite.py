#!/usr/bin/env python3
"""Render 21 offline preview assets (7 styles x 3 channels) from real FLUX images.

Requires one generated source image and a provenance receipt for EACH style.
Never generates paid images or publishes to social platforms. Missing sources
cause HOLD, not synthetic samples silently masquerading as real model output.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont
from scripts.zodiac_style_rotation import style_for_day
from scripts.text_safe_layout_gate import TrackedDraw
from scripts.visual_quality_gate import image_check,video_check,VisualHold

CHANNELS=("cardnews","shorts","threads")
TITLES={"cardnews":"오늘의 12지신 운세","shorts":"3초 만에 보는 오늘의 운세","threads":"당신의 띠에 찾아올 변화"}
SUBS={"cardnews":"행운이 찾아오는 순간","shorts":"당신의 행운을 확인하세요","threads":"띠별 풀이 · 프로필 링크"}
SOURCE_SIZE=(768,1344)
OUTPUT_SIZE=(1080,1920)
SUBJECT=[(97,519,983,1478)]
def _font(root:Path,size:int):
    f=root/"assets"/"fonts"/"Pretendard-Black.ttf"
    if f.is_file():return ImageFont.truetype(str(f),size)
    for path in ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).is_file():return ImageFont.truetype(path,size)
    raise RuntimeError("no Korean font")
def _cover(source:Path,output:Path,title:str,sub:str,project_root:Path):
    with Image.open(source) as im:
        rgb=im.convert("RGB")
        scale=max(1080/rgb.width,1920/rgb.height)
        rgb=rgb.resize((round(rgb.width*scale),round(rgb.height*scale)),Image.Resampling.LANCZOS)
        ox=(rgb.width-1080)//2;oy=(rgb.height-1920)//2
        bg=rgb.crop((ox,oy,ox+1080,oy+1920))
    dr=TrackedDraw(bg,SUBJECT,auto_shift=False)
    ft=_font(project_root,70);fs=_font(project_root,42)
    top_panel=(52,155,1028,400)
    bottom_panel=(62,1510,1018,1644)
    dr.panel(top_panel,radius=48,fill=(255,255,255,246))
    dr.panel(bottom_panel,radius=38,fill=(255,255,255,246))
    title_width=dr.textlength(title,font=ft)
    sub_width=dr.textlength(sub,font=fs)
    dr.text(((1080-title_width)/2,195),title,font=ft,fill=(25,28,43))
    dr.text(((1080-sub_width)/2,1548),sub,font=fs,fill=(36,40,50))
    report=dr.verify()
    output.parent.mkdir(parents=True,exist_ok=True)
    bg.save(output,"JPEG",quality=91,optimize=True)
    image_check(output,min_bytes=50000)
    return report

def render(source_root:Path,output_root:Path,project_root:Path,video=False):
    output_root.mkdir(parents=True,exist_ok=True)
    entries=[];missing=[]
    start=dt.date(2026,11,23)
    for idx in range(7):
        day=(start+dt.timedelta(days=idx)).isoformat()
        st=style_for_day(day);style_id=st["id"]
        src=source_root/(style_id+"_cover.png")
        receipt=source_root/(style_id+"_receipt.json")
        if not src.exists() or not receipt.exists():
            missing.append(style_id);continue
        provenance=json.loads(receipt.read_text(encoding="utf-8"))
        # This is a REVIEW-ONLY gallery, never publication eligible. Provenance
        # confirms model/source but does not assert all species were correct.
        if (provenance.get("provider")!="flux2_klein_local" or
            provenance.get("style_id")!=style_id or
            provenance.get("paid_api_calls")!=0 or
            hashlib.sha256(src.read_bytes()).hexdigest()!=provenance.get("sha256")):
            raise VisualHold("FLUX_PROVENANCE_MISMATCH_"+style_id)
        for channel in CHANNELS:
            target=output_root/f"{style_id}_{channel}.jpg"
            report=_cover(src,target,TITLES[channel],SUBS[channel],project_root)
            item={"style_id":style_id,"channel":channel,"image":str(target),
                  "layout_status":report["status"],"auto_fixes":report["auto_fixes"],
                  "provider":provenance["provider"],"sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
                  "paid_api_calls":0}
            if channel=="shorts" and video:
                mp4=target.with_suffix(".mp4")
                subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-loop","1","-i",str(target),
                                "-t","2","-r","12","-vf","format=yuv420p",
                                "-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p",str(mp4)],
                               check=True,timeout=90)
                item["mp4"]=str(mp4)
                item["video_quality"]=video_check(mp4,min_bytes=3000)
            entries.append(item)
    # A full gallery does not imply correct twelve-animal representation.
    # Content QA must come from an independent source, per image hash.
    result={"schema":"zodiac-7x3-preview-v1","status":"REVIEW_REQUIRED" if len(entries)==21 and not missing else "HOLD",
            "count":len(entries),"expected":21,"missing_real_flux_styles":missing,"samples":entries,
            "semantic_qa":"NOT_AUTOMATICALLY_VERIFIED",
            "paid_api_calls":0,"publication_attempts":0}
    (output_root/"preview_report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if len(entries)==21:
        tiles=[]
        for item in entries:
            with Image.open(item["image"]) as im:
                tiles.append(im.resize((216,384),Image.Resampling.LANCZOS))
        sheet=Image.new("RGB",(216*7,384*3),"white")
        for j,tile in enumerate(tiles):
            col=j//3;row=j%3
            sheet.paste(tile,(216*col,384*row))
        sheet.save(output_root/"zodiac_21_previews.jpg","JPEG",quality=90)
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--sources",type=Path,default=Path("/tmp/zodiac-seven-styles-real"))
    ap.add_argument("--output",type=Path,default=Path("/tmp/zodiac-seven-styles-review"))
    ap.add_argument("--videos",action="store_true")
    args=ap.parse_args()
    result=render(args.sources,args.output,Path(__file__).resolve().parents[1],args.videos)
    print(json.dumps({"status":result["status"],"count":result["count"],"missing":result["missing_real_flux_styles"],
                      "report":str(args.output/"preview_report.json"),"paid_api_calls":0},ensure_ascii=False))
    return 0 if result["count"]==21 else 2  # preview existence only; semantic QA is separate
if __name__=="__main__":
    raise SystemExit(main())
