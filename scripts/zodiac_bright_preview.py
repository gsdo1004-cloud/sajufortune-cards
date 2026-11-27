"""Bright card renderer and offline QA export. Never publishes or writes approvals."""
from pathlib import Path
import datetime as dt
import json
from PIL import Image, ImageDraw, ImageFont
from scripts.text_safe_layout_gate import check_layout, contrast_ratio, intersects, LayoutHold
from scripts.zodiac_character_prompts import STEMS, protected_boxes
from scripts.zodiac_semantic_qa_gate import face_boxes_for
from scripts.flux_first_card_assets import verify
from scripts.visual_quality_gate import sha256
import zodiac_cardnews_tpl as t
import zodiac_topview as zt

PALETTES = {
    "A": {"red":"#C81D25","blue":"#164BC5","yellow":"#FFD60A","ink":"#101828","sub":"#344054","bars":["#FF3B30","#2563EB","#FFD60A"]},
    "B": {"red":"#B92343","blue":"#2452B8","yellow":"#FFE36B","ink":"#16243A","sub":"#344054","bars":["#FF5A5F","#3B82F6","#34D399"]},
}
WHITE = "#FFFFFF"
# Four editorial treatments rotate independently of the seven mascot styles.
# A is the user-reviewed reference; all variants retain the same protected grid.
DESIGNS = {
    "PRIMARY_A": {"title_bg":"#164BC5","title_fg":"#FFFFFF","date_bg":"#FFD60A","date_fg":"#101828","cta_bg":"#C81D25","cta_fg":"#FFFFFF","radius":35,"date_half":335,"bars":["#FF3B30","#2563EB","#FFD60A"]},
    "PRIMARY_RED": {"title_bg":"#C81D25","title_fg":"#FFFFFF","date_bg":"#164BC5","date_fg":"#FFFFFF","cta_bg":"#FFD60A","cta_fg":"#101828","radius":18,"date_half":370,"bars":["#2563EB","#FFD60A","#FF3B30"]},
    "PRIMARY_YELLOW": {"title_bg":"#FFD60A","title_fg":"#101828","date_bg":"#C81D25","date_fg":"#FFFFFF","cta_bg":"#164BC5","cta_fg":"#FFFFFF","radius":50,"date_half":350,"bars":["#FFD60A","#FF3B30","#2563EB"]},
    "PRIMARY_WHITE": {"title_bg":"#FFFFFF","title_fg":"#164BC5","date_bg":"#FFD60A","date_fg":"#101828","cta_bg":"#C81D25","cta_fg":"#FFFFFF","radius":12,"date_half":385,"bars":["#FF3B30","#FFD60A","#2563EB"]},
}
def design_for_day(day):
    # Monday 2026-12-07 was the approved A preview.
    return tuple(DESIGNS)[(dt.date.fromisoformat(day)-dt.date(2026,12,7)).days % len(DESIGNS)]

def production_palette(day):
    key=design_for_day(day)
    return {**PALETTES["A"],**DESIGNS[key]}


def rgb(s):
    return tuple(bytes.fromhex(s.lstrip("#")))

class Canvas:
    def __init__(self, im, protected, palette):
        self.im=im; self.dr=ImageDraw.Draw(im); self.protected=protected
        self.p=palette; self.texts=[]; self.panels=[]; self.ratios=[]; self.sizes=[]
    def panel(self,b,fill=WHITE,radius=24):
        self.panels.append(tuple(b))
        self.dr.rounded_rectangle(b,radius=radius,fill=fill)
    def text(self,xy,s,size,fg,bg=WHITE,*,center=False,area=None):
        f=t.F("Pretendard-Black.ttf",size)
        x,y=xy
        if center: x-=self.dr.textlength(s,font=f)/2
        b=self.dr.textbbox((x,y),s,font=f,anchor="lt")
        if area and not (area[0]<=b[0] and area[1]<=b[1] and b[2]<=area[2] and b[3]<=area[3]):
            raise LayoutHold("PREVIEW_TEXT_OUTSIDE_PANEL:"+s)
        if any(intersects(b,q,2) for q in self.texts):
            raise LayoutHold("PREVIEW_TEXT_OVERLAP:"+s)
        ratio=contrast_ratio(rgb(fg),rgb(bg))
        if ratio<4.5: raise LayoutHold("PREVIEW_LOW_CONTRAST:"+s)
        self.dr.text((x,y),s,font=f,fill=fg,anchor="lt")
        self.texts.append(b);self.ratios.append(ratio);self.sizes.append(size)
    def wrap(self,s,size,width):
        f=t.F("Pretendard-Black.ttf",size)
        lines=[]; cur=""
        for word in s.split():
            candidate=(cur+" "+word).strip()
            if self.dr.textlength(candidate,font=f)<=width: cur=candidate
            else:
                if cur: lines.append(cur)
                cur=word
                if self.dr.textlength(cur,font=f)>width: raise LayoutHold("PREVIEW_WORD_TOO_WIDE")
        if cur: lines.append(cur)
        return lines
    def finish(self):
        report=check_layout(self.texts,self.protected,1080,1920,self.panels)
        if report["status"]!="PASS": raise LayoutHold(str(report["reason_codes"]))
        report.update(actual_min_text_contrast=round(min(self.ratios),2),min_font_px=min(self.sizes),preview_only=True)
        return report

def render_card(source,day,stem,rows,palette):
    im=Image.open(source/"assets"/"flux_daily"/day/(stem+".jpg")).convert("RGB")
    c=Canvas(im,protected_boxes(stem,1080,1920)+face_boxes_for(day,stem,source),palette)
    p=c.p; ink=p["ink"];sub=p["sub"];blue=p["blue"];red=p["red"];yellow=p["yellow"]
    idx=STEMS.index(stem)
    title_bg=p.get("title_bg",blue);title_fg=p.get("title_fg",WHITE)
    date_bg=p.get("date_bg",yellow);date_fg=p.get("date_fg",ink)
    cta_bg=p.get("cta_bg",red);cta_fg=p.get("cta_fg",WHITE)
    radius=p.get("radius",35);half=p.get("date_half",335)
    if idx==0:
        b=(58,65,1022,228);c.panel(b,title_bg,radius);c.text((540,84),"오늘의 운세",118,title_fg,title_bg,center=True,area=b)
        b=(540-half,252,540+half,340);c.panel(b,date_bg,30);c.text((540,269),t.date_full(day),51,date_fg,date_bg,center=True,area=b)
        b=(64,1540,1016,1650);c.panel(b,cta_bg,33);c.text((540,1560),"12띠 전체 흐름",63,cta_fg,cta_bg,center=True,area=b)
    elif idx<=4:
        b=(48,42,1032,142);c.panel(b,title_bg,radius);c.text((540,66),"오늘의 띠별운세 · "+t.date_full(day),45,title_fg,title_bg,center=True,area=b)
        for i,ko in enumerate(t.CARD_GROUPS[idx-1]):
            r=rows[ko]; y=220+i*490; b=(350,y,1040,y+354);c.panel(b)
            # Bright strips are decorative, not a substitute for readable labels.
            c.dr.rounded_rectangle((360,y+18,374,y+336),radius=7,fill=p["bars"][i])
            c.text((394,y+21),ko,70,ink,area=b)
            lines=c.wrap(r["line"],48,624)
            if len(lines)>2: raise LayoutHold("PREVIEW_GROUP_LINE_OVERFLOW")
            for j,line in enumerate(lines): c.text((394,y+112+j*56),line,48,sub,area=b)
            for j,label in enumerate(("전체","금전","연애","건강")):
                x=394+(j%2)*320; yy=y+239+(j//2)*52
                c.text((x,yy),label+" "+t.stars(r["stars"][label]),42,red if j==0 else blue,area=b)
    else:
        b=(48,42,1032,142);c.panel(b,title_bg,radius);c.text((540,66),"12띠 총정리 · "+t.date_full(day),45,title_fg,title_bg,center=True,area=b)
        order=[ko for group in t.CARD_GROUPS for ko in group]
        for i,ko in enumerate(order):
            x=44+(i%2)*504;y=175+(i//2)*225;b=(x,y,x+488,y+213)
            c.panel(b)
            r=rows[ko]
            c.text((x+20,y+12),ko,56,ink,area=b)
            c.text((x+20,y+75),"전체 "+t.stars(r["stars"]["전체"]),42,red,area=b)
            lines=c.wrap(r["line"],37,448)
            if len(lines)>2: raise LayoutHold("PREVIEW_SUMMARY_LINE_OVERFLOW")
            for j,line in enumerate(lines): c.text((x+20,y+122+j*42),line,37,sub,area=b)
    return im,c.finish()

def preview(source:Path,day:str,out:Path,variant:str):
    source=source.resolve();out=out.resolve()
    if out.exists() or source==out or source in out.parents or out.name not in ("A","B"):
        raise ValueError("preview requires a fresh independent A/B directory")
    m=verify(day,source)
    if not m.get("style_id"): raise LayoutHold("PREVIEW_REQUIRES_STYLED_SOURCE")
    rows=zt.build_rows(day)
    results=[]
    for i,stem in enumerate(STEMS,1):
        im,report=render_card(source,day,stem,rows,PALETTES[variant]);results.append((im,report))
    out.mkdir(parents=True)
    reports=[]
    for i,(im,report) in enumerate(results,1):
        p=out/f"preview_{i:02d}.jpg"; im.save(p,quality=92);report["sha256"]=sha256(p);reports.append(report)
    result={"status":"PREVIEW_ONLY","publication_eligible":False,"style":m["style_id"],"date":day,"variant":variant,"source_manifest_sha256":sha256(source/"assets"/"flux_daily"/day/"manifest.json"),"reports":reports,"paid_api_calls":0}
    (out/"preview_qa.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result
