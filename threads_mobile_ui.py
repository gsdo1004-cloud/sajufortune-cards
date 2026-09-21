#!/usr/bin/env python3
from __future__ import annotations
import hashlib,re
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
MAX_AGE_HOURS=36
BLOCKED=('http://','https://','www.','sajufortune','구매','결제','프로필 링크')
@dataclass
class UiJob:
 target_id:str; username:str; post_text:str; published_at:str; comment:str; status:str='DISCOVERED'; receipt:str=''
 @property
 def key(self):
  norm=re.sub(r'\s+',' ',self.comment.strip()).lower()
  return hashlib.sha256(f'{self.target_id}|{self.username.lower()}|{norm}'.encode()).hexdigest()[:24]
def parse_dt(v):
 d=datetime.fromisoformat(v.replace('Z','+00:00')); return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
def qualify(job,now=None):
 now=now or datetime.now(timezone.utc); age=now-parse_dt(job.published_at).astimezone(timezone.utc)
 if age<timedelta(0) or age>timedelta(hours=MAX_AGE_HOURS): return False,'stale'
 if any(x.lower() in job.comment.lower() for x in BLOCKED): return False,'promotional'
 if '#' in job.comment or '@' in job.comment: return False,'tagged'
 if len(job.comment.strip())<12: return False,'too_short'
 return True,'ok'
def transition(job,new):
 allowed={'DISCOVERED':{'READY_UI','FAILED'},'READY_UI':{'OPENED','FAILED'},'OPENED':{'COMPOSED','FAILED'},'COMPOSED':{'SUBMITTED','FAILED'},'SUBMITTED':{'VERIFIED','FAILED_UNVERIFIED'},'VERIFIED':set(),'FAILED':set(),'FAILED_UNVERIFIED':set()}
 if new not in allowed.get(job.status,set()): raise ValueError(f'invalid transition {job.status}->{new}')
 job.status=new; return job
def verify_compose(actual,expected): return actual==expected
def verify_receipt(ui_text,account,comment): return account in ui_text and comment in ui_text
