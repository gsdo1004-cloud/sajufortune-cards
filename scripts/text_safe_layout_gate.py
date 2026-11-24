"""Measured PIL text boxes against protected subject regions, with bounded correction.

Protection zones come from the prompt composition contract, NOT automatic
animal-face detection; independent vision QA remains essential.
"""
from PIL import ImageDraw
class LayoutHold(ValueError):pass
def intersects(a,b,pad=0):
    return a[0]<b[2]+pad and a[2]>b[0]-pad and a[1]<b[3]+pad and a[3]>b[1]-pad
def within(b,w,h):
    return 4<=b[0]<b[2]<=w-4 and 4<=b[1]<b[3]<=h-4
def contrast_ratio(fg=(28,28,38),bg=(255,255,255)):
    def lum(rgb):
        v=[p/255 for p in rgb[:3]]
        v=[p/12.92 if p<=.04045 else ((p+.055)/1.055)**2.4 for p in v]
        return .2126*v[0]+.7152*v[1]+.0722*v[2]
    a,b=sorted((lum(fg),lum(bg)),reverse=True)
    return (a+.05)/(b+.05)
def check_layout(texts,protected,w,h,panels=(),min_contrast=4.5):
    texts,protected,panels=list(texts),list(protected),list(panels)
    if not texts:raise LayoutHold("no measured text boxes")
    reasons=[]
    for i,b in enumerate(texts):
        if not within(b,w,h):reasons.append(f"TEXT_OUTSIDE_{i}")
        if any(intersects(b,p,6) for p in protected):reasons.append(f"TEXT_SUBJECT_OVERLAP_{i}")
    for i,b in enumerate(panels):
        if not within(b,w,h):reasons.append(f"PANEL_OUTSIDE_{i}")
        if any(intersects(b,p,5) for p in protected):reasons.append(f"PANEL_SUBJECT_OVERLAP_{i}")
    ratio=contrast_ratio()
    if ratio<min_contrast:reasons.append("LOW_CONTRAST")
    return {"status":"PASS" if not reasons else "HOLD","reason_codes":reasons,
            "measured_text_boxes":texts,"panel_boxes":panels,
            "protected_regions":protected,
            "protection_source":"composition_contract_not_face_detection",
            "contrast_ratio":round(ratio,2)}
def reposition(b,protected,w,h,occupied=(),step=12):
    candidates=[(0,0)]
    for j in range(1,26):
        d=j*step
        candidates.extend([(d,0),(-d,0),(0,d),(0,-d),(d,-d),(-d,-d),(d,d),(-d,d)])
    for dx,dy in candidates:
        q=(b[0]+dx,b[1]+dy,b[2]+dx,b[3]+dy)
        if not within(q,w,h):continue
        if any(intersects(q,r,9) for r in protected):continue
        if any(intersects(q,r,2) for r in occupied):continue
        return dx,dy
    return None
class TrackedDraw:
    def __init__(self,image,protected=(),auto_shift=True):
        self._image=image;self._draw=ImageDraw.Draw(image,"RGBA")
        self.protected=list(protected);self.auto_shift=auto_shift
        self.text_boxes=[];self.panel_boxes=[];self.fixes=[]
    def __getattr__(self,name):return getattr(self._draw,name)
    def panel(self,b,fill,radius=0,**kw):
        b=tuple(map(int,b));self.panel_boxes.append(b)
        if radius:return self._draw.rounded_rectangle(b,radius=radius,fill=fill,**kw)
        return self._draw.rectangle(b,fill=fill,**kw)
    def text(self,xy,text,*args,**kw):
        b=tuple(map(int,self._draw.textbbox(xy,text,font=kw.get("font"),stroke_width=kw.get("stroke_width",0))))
        if any(intersects(b,p,6) for p in self.protected):
            delta=reposition(b,self.protected,self._image.width,self._image.height,self.text_boxes) if self.auto_shift else None
            if delta is None:raise LayoutHold("TEXT_SUBJECT_OVERLAP_NO_REPAIR")
            xy=(xy[0]+delta[0],xy[1]+delta[1])
            b=(b[0]+delta[0],b[1]+delta[1],b[2]+delta[0],b[3]+delta[1])
            self.fixes.append({"type":"text_shift","dx":delta[0],"dy":delta[1]})
        self.text_boxes.append(b)
        return self._draw.text(xy,text,*args,**kw)
    def verify(self):
        r=check_layout(self.text_boxes,self.protected,self._image.width,self._image.height,self.panel_boxes)
        r["auto_fixes"]=self.fixes
        if r["status"]!="PASS":raise LayoutHold(",".join(r["reason_codes"]))
        return r
