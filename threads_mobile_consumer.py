from __future__ import annotations
import base64,os,re,subprocess,time,xml.etree.ElementTree as ET
from dataclasses import dataclass
ADB='/mnt/c/Users/gsd10/AppData/Local/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe'
BRIDGE='com.sajufortune.imebridge/.BridgeImeService'; SAMSUNG='com.samsung.android.honeyboard/.service.HoneyBoardService'
@dataclass
class Result: status:str; detail:str=''
def connected_devices():
 out=subprocess.run([ADB,'devices'],capture_output=True,text=True,check=True).stdout
 return [ln.split()[0] for ln in out.splitlines()[1:] if ln.strip().endswith('\tdevice')]
def choose_device(preferred='RFCX60EHW9W'):
 ds=connected_devices()
 if preferred in ds: return preferred
 if len(ds)==1: return ds[0]
 raise RuntimeError('device_missing_or_ambiguous')
def run(serial,*args): return subprocess.run([ADB,'-s',serial,*args],capture_output=True,text=True,check=True).stdout
def open_target(serial,permalink,username):
 if not permalink: return Result('FAILED','permalink_missing')
 run(serial,'shell','am','start','-a','android.intent.action.VIEW','-d',permalink,'com.instagram.barcelona'); time.sleep(2)
 root=dump(serial); blob='\n'.join(x for n in root.iter() for x in (n.attrib.get('text',''),n.attrib.get('content-desc','')))
 if username and username not in blob: return Result('FAILED','target_username_mismatch')
 if composer(root) is None: return Result('FAILED','target_composer_missing')
 return Result('TARGET_VERIFIED','permalink_username_composer')
def bounds_center(b):
 a=list(map(int,re.findall(r'\d+',b))); return (a[0]+a[2])//2,(a[1]+a[3])//2
def dump(serial,path='/sdcard/ui.xml'):
 run(serial,'shell','uiautomator','dump',path); raw=run(serial,'shell','cat',path); return ET.fromstring(raw)
def composer(root):
 return next((n for n in root.iter() if n.attrib.get('resource-id')=='permalink_inline_composer'),None)
def exact(root,text):
 n=composer(root); return n is not None and n.attrib.get('text','')==text
def receipt(root,account,text):
 s='\n'.join(x for n in root.iter() for x in (n.attrib.get('text',''),n.attrib.get('content-desc',''))); return account in s and text in s
def submit_control(root):
 # Threads currently exposes submit as an unlabeled clickable View to the right of attachment.
 # Accept only the narrow geometric signature after exact composer verification.
 c=composer(root)
 if c is None: return None
 for n in root.iter():
  if n.attrib.get('clickable')!='true' or n.attrib.get('class')!='android.view.View': continue
  b=n.attrib.get('bounds',''); a=list(map(int,re.findall(r'\d+',b)))
  if len(a)==4 and a[0]>=900 and a[2]>=1040 and 1800<=a[1]<=2100 and a[3]<=2200: return n
 return None
def input_exact(serial,text):
 run(serial,'shell','ime','set',BRIDGE); root=dump(serial); c=composer(root)
 if c is None: return Result('FAILED','composer_missing')
 x,y=bounds_center(c.attrib['bounds']); run(serial,'shell','input','tap',str(x),str(y))
 b64=base64.b64encode(text.encode()).decode(); run(serial,'shell','am','broadcast','-a','com.sajufortune.imebridge.SET_TEXT','--es','b64',b64); time.sleep(1)
 root=dump(serial)
 if not exact(root,text): return Result('FAILED','exact_guard')
 return Result('COMPOSED','exact')
def submit_once(serial,account,text):
 root=dump(serial)
 if not exact(root,text): return Result('FAILED','pre_submit_exact_guard')
 ctl=submit_control(root)
 if ctl is None: return Result('FAILED','submit_control_missing')
 x,y=bounds_center(ctl.attrib['bounds']); run(serial,'shell','input','tap',str(x),str(y))
 for delay in (2,2,3):
  time.sleep(delay); root=dump(serial)
  if receipt(root,account,text): return Result('VERIFIED','receipt_exact_account_text')
 return Result('FAILED_UNVERIFIED','no_retry_after_bounded_receipt_reads')
def restore_keyboard(serial):
 try: run(serial,'shell','ime','set',SAMSUNG)
 except Exception: pass

def process_queue_once(serial=None, account='gsdo10042026', at=None, live=False):
    import threads_publish_queue as q
    if not live or os.environ.get('THREADS_MOBILE_UI_LIVE') != '1': return Result('DRY_RUN','mobile_live_gate_disabled')
    serial=serial or choose_device()
    q.recover_expired(at)
    items=[x for x in q.due(at) if x.get('kind')=='threads_ui_reply']
    if not items: return Result('IDLE','no_due_ui_reply')
    item=items[0]; key=str(item['key']); claimed=q.claim(key,at)
    if not claimed.get('ok'): return Result('FAILED','claim_failed')
    payload=claimed['item'].get('payload') or {}; text=str(payload.get('text','')); permalink=str(payload.get('permalink','')); username=str(payload.get('username',''))
    try:
        if not text:
            q.fail(key,'empty_text',at); return Result('FAILED','empty_text')
        target=open_target(serial,permalink,username)
        if target.status!='TARGET_VERIFIED':
            q.fail(key,target.detail,at); return target
        composed=input_exact(serial,text)
        if composed.status!='COMPOSED':
            q.fail(key,composed.detail,at); return composed
        result=submit_once(serial,account,text)
        if result.status=='VERIFIED':
            q.complete_ui(key,{'account':account,'exact_text':text,'permalink':permalink,'username':username,'method':'uiautomator_exact_receipt'},at)
        elif result.status=='FAILED_UNVERIFIED':
            q.fail_unverified(key,result.detail,at)
        else:
            q.fail(key,result.detail,at)
        return result
    finally:
        restore_keyboard(serial)
