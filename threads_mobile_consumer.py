from __future__ import annotations
import base64,re,subprocess,time,xml.etree.ElementTree as ET
from dataclasses import dataclass
ADB='/mnt/c/Users/gsd10/AppData/Local/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe'
BRIDGE='com.sajufortune.imebridge/.BridgeImeService'; SAMSUNG='com.samsung.android.honeyboard/.service.HoneyBoardService'
@dataclass
class Result: status:str; detail:str=''
def run(serial,*args): return subprocess.run([ADB,'-s',serial,*args],capture_output=True,text=True,check=True).stdout
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
 x,y=bounds_center(ctl.attrib['bounds']); run(serial,'shell','input','tap',str(x),str(y)); time.sleep(2)
 root=dump(serial)
 return Result('VERIFIED','receipt') if receipt(root,account,text) else Result('FAILED_UNVERIFIED','no_retry')
def restore_keyboard(serial):
 try: run(serial,'shell','ime','set',SAMSUNG)
 except Exception: pass

def process_queue_once(serial, account='gsdo10042026', at=None):
    import threads_publish_queue as q
    q.recover_expired(at)
    items=[x for x in q.due(at) if x.get('kind')=='threads_ui_reply']
    if not items: return Result('IDLE','no_due_ui_reply')
    item=items[0]; key=str(item['key']); claimed=q.claim(key,at)
    if not claimed.get('ok'): return Result('FAILED','claim_failed')
    payload=claimed['item'].get('payload') or {}; text=str(payload.get('text',''))
    try:
        if not text:
            q.fail(key,'empty_text',at); return Result('FAILED','empty_text')
        composed=input_exact(serial,text)
        if composed.status!='COMPOSED':
            q.fail(key,composed.detail,at); return composed
        result=submit_once(serial,account,text)
        if result.status=='VERIFIED':
            q.complete(key,'ui-verified:'+key,at)
        elif result.status=='FAILED_UNVERIFIED':
            q.fail_unverified(key,result.detail,at)
        else:
            q.fail(key,result.detail,at)
        return result
    finally:
        restore_keyboard(serial)
