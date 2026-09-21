import os,tempfile,unittest
from pathlib import Path
import threads_publish_queue as q
class T(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(); q.STATE=Path(self.t.name)/'q.jsonl'; q.AUDIT=Path(self.t.name)/'a.jsonl'
 def tearDown(self): self.t.cleanup()
 def test_payload_and_terminal_unverified(self):
  r=q.enqueue('k','2026-01-01T00:00:00+00:00','threads_ui_reply','target',{'text':'안녕'},max_retries=0); self.assertEqual(r['item']['payload']['text'],'안녕')
  self.assertTrue(q.claim('k','2026-01-01T00:00:01+00:00')['ok']); x=q.fail_unverified('k'); self.assertEqual(x['item']['status'],'FAILED_UNVERIFIED'); self.assertEqual(q.due('2030-01-01T00:00:00+00:00'),[])
if __name__=='__main__': unittest.main()

class ConsumerQueueTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(); q.STATE=Path(self.t.name)/'q.jsonl'; q.AUDIT=Path(self.t.name)/'a.jsonl'
 def tearDown(self): self.t.cleanup()
 def test_consumer_verified_completes(self):
  import threads_mobile_consumer as c
  q.enqueue('v','2026-01-01T00:00:00+00:00','threads_ui_reply','t',{'text':'좋은 글입니다'},max_retries=0)
  oi,osub,or_,ot=c.input_exact,c.submit_once,c.restore_keyboard,c.open_target
  try:
   os.environ['THREADS_MOBILE_UI_LIVE']='1'; c.open_target=lambda *a:c.Result('TARGET_VERIFIED','ok'); c.input_exact=lambda *a:c.Result('COMPOSED','exact'); c.submit_once=lambda *a:c.Result('VERIFIED','receipt'); c.restore_keyboard=lambda *a:None
   r=c.process_queue_once('SER','acct','2026-01-01T00:00:01+00:00',live=True); self.assertEqual(r.status,'VERIFIED'); self.assertEqual(q.load()[0]['status'],'PUBLISHED')
  finally: c.input_exact,c.submit_once,c.restore_keyboard,c.open_target=oi,osub,or_,ot; os.environ.pop('THREADS_MOBILE_UI_LIVE',None)
 def test_consumer_unverified_is_terminal(self):
  import threads_mobile_consumer as c
  q.enqueue('u','2026-01-01T00:00:00+00:00','threads_ui_reply','t',{'text':'좋은 글입니다'},max_retries=0)
  oi,osub,or_,ot=c.input_exact,c.submit_once,c.restore_keyboard,c.open_target
  try:
   os.environ['THREADS_MOBILE_UI_LIVE']='1'; c.open_target=lambda *a:c.Result('TARGET_VERIFIED','ok'); c.input_exact=lambda *a:c.Result('COMPOSED','exact'); c.submit_once=lambda *a:c.Result('FAILED_UNVERIFIED','no_retry'); c.restore_keyboard=lambda *a:None
   r=c.process_queue_once('SER','acct','2026-01-01T00:00:01+00:00',live=True); self.assertEqual(r.status,'FAILED_UNVERIFIED'); self.assertEqual(q.load()[0]['status'],'FAILED_UNVERIFIED')
  finally: c.input_exact,c.submit_once,c.restore_keyboard,c.open_target=oi,osub,or_,ot; os.environ.pop('THREADS_MOBILE_UI_LIVE',None)
