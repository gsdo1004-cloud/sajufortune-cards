"""Read-only media integrity gate; no publishing and no billable providers."""
from __future__ import annotations
import hashlib,json,subprocess,shutil,io
from pathlib import Path
from PIL import Image,ImageStat,ImageFilter
class VisualHold(ValueError):pass
def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def image_check(path, size=(1080,1920), min_bytes=50000):
    p=Path(path)
    if not p.is_file() or p.stat().st_size<min_bytes:raise VisualHold("IMAGE_MISSING_OR_SMALL")
    try:
        with Image.open(p) as im:
            im.verify()
        with Image.open(p) as im:
            if im.size!=size:raise VisualHold("WRONG_IMAGE_DIMENSIONS")
            rgb=im.convert("RGB")
            stat=ImageStat.Stat(rgb)
            if max(stat.stddev)<9:raise VisualHold("BLANK_IMAGE")
            if sum(stat.mean)/3<12:raise VisualHold("BLACK_IMAGE")
    except (OSError,SyntaxError) as e:raise VisualHold("CORRUPTED_IMAGE") from e
    return {"status":"PASS","size_bytes":p.stat().st_size,"sha256":sha256(p)}
def video_check(path, max_duration=None, min_bytes=90000, *, sample_frames=True):
    p=Path(path)
    if not p.is_file() or p.stat().st_size<min_bytes:raise VisualHold("VIDEO_MISSING_OR_SMALL")
    if not shutil.which("ffprobe"):raise VisualHold("FFPROBE_UNAVAILABLE")
    try:
        q=subprocess.run(["ffprobe","-v","error","-show_entries","stream=codec_type,codec_name,width,height:format=duration",
                          "-of","json",str(p)],capture_output=True,text=True,timeout=30,check=True)
        obj=json.loads(q.stdout)
    except (ValueError,OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError) as e:
        raise VisualHold("VIDEO_PROBE_FAILED") from e
    video=next((s for s in obj.get("streams",[]) if s.get("codec_type")=="video"),None)
    dur=float(obj.get("format",{}).get("duration") or 0)
    if not video or video.get("codec_name") not in ("h264","hevc","av1") or dur<=0:
        raise VisualHold("VIDEO_CODEC_OR_DURATION")
    if video.get("width") !=1080 or video.get("height") !=1920:
        raise VisualHold("VIDEO_WRONG_FRAME")
    if max_duration is not None and dur>max_duration:raise VisualHold("VIDEO_TOO_LONG")
    samples=[]
    if sample_frames:
        if not shutil.which("ffmpeg"):raise VisualHold("FFMPEG_UNAVAILABLE")
        for t in (0.05,max(.1,dur/2),max(0.05,dur-1.0)):
            try:
                r=subprocess.run(["ffmpeg","-nostdin","-v","error","-ss",str(t),"-i",str(p),
                                  "-frames:v","1","-threads:v","1","-f","image2pipe","-vcodec","mjpeg","-"],
                                 capture_output=True,timeout=35,check=True)
                if not r.stdout:
                    raise VisualHold("VIDEO_FRAME_EMPTY")
                with Image.open(io.BytesIO(r.stdout)) as im:
                    st=ImageStat.Stat(im.convert("RGB"))
                    brightness=sum(st.mean)/3
                    if brightness<9 or max(st.stddev)<5:raise VisualHold("BLACK_OR_BLANK_VIDEO_FRAME")
                    samples.append({"at_seconds":round(t,2),"mean_brightness":round(brightness,2)})
            except (OSError,subprocess.TimeoutExpired,subprocess.CalledProcessError,ValueError) as e:
                raise VisualHold("VIDEO_FRAME_DECODE_FAILED") from e
    return {"status":"PASS","duration_seconds":dur,"codec":video.get("codec_name"),
            "size_bytes":p.stat().st_size,"sha256":sha256(p),"sample_frames":samples}

def underlay_detail_check(image, boxes, threshold=.049):
    """Heuristic: flag dense illustration *beneath* intended text panels.

    Edge density cannot identify actual faces or species. It is a conservative
    supplement to geometry + independently verified semantic identity.
    """
    rgb=image.convert("RGB")
    findings=[]
    for box in boxes:
        if not (0<=box[0]<box[2]<=rgb.width and 0<=box[1]<box[3]<=rgb.height):
            raise VisualHold("UNDERLAY_BOX_OUTSIDE")
        crop=rgb.crop(box).convert("L").filter(ImageFilter.FIND_EDGES)
        hist=crop.histogram()
        density=sum(hist[35:])/max(1,sum(hist))
        findings.append({"box":list(box),"edge_density":round(density,4),
                         "status":"HOLD" if density>threshold else "PASS"})
    return {"status":"PASS" if all(x["status"]=="PASS" for x in findings) else "HOLD",
            "method":"heuristic_edge_density_not_face_detection",
            "threshold":threshold,"regions":findings}
