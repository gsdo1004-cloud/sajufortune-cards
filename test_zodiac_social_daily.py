import datetime as dt,json,os,unittest
from unittest.mock import patch,Mock
from pathlib import Path
import zodiac_social_daily as z

DAY='2026-11-24'
NOW=dt.datetime(2026,11,24,18,15,tzinfo=z.KST)
META={'date':DAY,'contract':'zodiac12-avatar-safe-v2','zodiac_signs':z.SIGNS,'narration':['11월 24일 '+'. '.join(s+', 차분하게 행동하기 좋은 날입니다' for s in z.SIGNS)+'.']}
class FakeGH:
    def __init__(self):self.files={};self.writes=[];self.fail_claim=False;self.fail_receipt=False
    def existing(self,p):return self.files.get(p)
    def head(self):return 'a'*40
    def put(self,p,data,message,old_sha=None):
        if (self.fail_claim and 'social_claim_' in p) or (self.fail_receipt and 'pub_reels' in p):raise RuntimeError('remote write failure')
        if p in self.files and old_sha is None:raise RuntimeError('conflict')
        self.files[p]=json.loads(data);self.writes.append(p);return {'content':{'sha':'claim-sha'},'commit':{'sha':'a'*40}}
def fetch(url,*a):
    if url.endswith('shorts_meta.json'):return json.dumps(META).encode()
    if url.endswith('uploaded.json'):return json.dumps({'date':DAY,'video_id':'v'}).encode()
    return b'mp4 data'
class Safety(unittest.TestCase):
    def setUp(self):
        self.gh=FakeGH();self.addCleanup(patch.stopall)
        self.get=patch.object(z,'public_get',side_effect=fetch).start()
        patch.object(z,'probe',return_value=68).start()
        patch('media_preflight.check_public_media',return_value=(True,'ok')).start()
        patch.dict(os.environ,{'THREADS_EXPECTED_USERNAME':'gsdo10042026','THREADS_ACCESS_TOKEN':'fake'}).start()
        patch('zodiac_cardnews._threads_uid',return_value='uid').start()
        self.send=patch('zodiac_reels.publish_video',return_value='123').start()
    def run_publish(self,live=True,now=NOW):return z.publish('threads_short',DAY,self.gh,live,now)
    def test_dry_run_never_writes_or_sends(self):
        self.assertEqual(self.run_publish(False),'DRY_RUN');self.assertEqual(self.gh.writes,[]);self.send.assert_not_called()
    def test_existing_receipt_skips_before_fetch(self):
        self.gh.files[z.marker('threads_short',DAY)]={'post_id':'999'};self.assertEqual(self.run_publish(),'SKIP');self.get.assert_not_called();self.send.assert_not_called()
    def test_existing_claim_holds_before_fetch(self):
        self.gh.files[z.claim_path('threads_short',DAY)]={'state':'PUBLISHING'};self.assertEqual(self.run_publish(),'SKIP');self.get.assert_not_called();self.send.assert_not_called()
    def test_claim_write_fail_no_send(self):
        self.gh.fail_claim=True
        with self.assertRaises(RuntimeError):self.run_publish()
        self.send.assert_not_called()
    def test_claim_exists_before_send_and_once(self):
        def send(*a):
            self.assertEqual(self.gh.files[z.claim_path('threads_short',DAY)]['state'],'PUBLISHING');self.assertNotIn(z.marker('threads_short',DAY),self.gh.files);return '123'
        self.send.side_effect=send;self.assertEqual(self.run_publish(),'PUBLISHED');self.assertEqual(self.run_publish(),'SKIP');self.send.assert_called_once()
        self.assertEqual(self.gh.files[z.marker('threads_short',DAY)]['post_id'],'123')
    def test_ambiguous_send_failure_holds_retry(self):
        self.send.side_effect=TimeoutError('response lost')
        with self.assertRaises(TimeoutError):self.run_publish()
        self.assertEqual(self.run_publish(),'SKIP');self.send.assert_called_once();self.assertNotIn(z.marker('threads_short',DAY),self.gh.files)
    def test_receipt_write_failure_holds_retry(self):
        self.gh.fail_receipt=True
        with self.assertRaises(RuntimeError):self.run_publish()
        self.assertEqual(self.run_publish(),'SKIP');self.send.assert_called_once()
    def test_wrong_account_blocks(self):
        with patch.dict(os.environ,{'THREADS_EXPECTED_USERNAME':'shopping'}):
            with self.assertRaises(RuntimeError):self.run_publish()
        self.send.assert_not_called();self.assertEqual(self.gh.writes,[])
    def test_late_slot_blocks(self):
        with self.assertRaises(RuntimeError):self.run_publish(now=NOW.replace(hour=23))
        self.send.assert_not_called()
    def test_source_contract_and_signs(self):
        for change in ({'contract':'flux-v3'},{'date':'2026-11-25'},{'zodiac_signs':z.SIGNS[:-1]},{'flux':'new'}):
            with self.assertRaises(RuntimeError):z.decode_meta(json.dumps({**META,**change}).encode(),DAY)
    def test_primary_short_reuses_old_marker(self):
        self.gh.files[z.marker('ig_short',DAY)]={'post_id':'123'}
        self.assertEqual(z.publish('ig_short',DAY,self.gh,True,NOW),'SKIP');self.get.assert_not_called()
    def test_distinct_image_and_short_receipts(self):self.assertNotEqual(z.marker('ig_image',DAY),z.marker('ig_short',DAY))
    def test_future_signed_release_guard_blocks(self):
        self.gh.files['scripts/zodiac_publish_guard.py']={'sha':'guard'}
        with self.assertRaises(RuntimeError):self.run_publish()
        self.send.assert_not_called();self.get.assert_not_called()
    def test_ig_short_claim_before_send_and_receipt(self):
        with patch('zodiac_instagram._account_key',return_value='gsdo10042026'), patch('zodiac_instagram._expected_username',return_value='gsdo10042026'), patch('zodiac_instagram.preflight',return_value=True), patch('zodiac_instagram.publish_reel',return_value='123') as send:
            self.assertEqual(z.publish('ig_short',DAY,self.gh,True,NOW),'PUBLISHED');self.assertEqual(z.publish('ig_short',DAY,self.gh,True,NOW),'SKIP');send.assert_called_once()
            receipt=self.gh.files[z.marker('ig_short',DAY)];self.assertEqual(receipt['kind'],'reel');self.assertEqual(receipt['post_id'],'123')
    def test_ig_wrong_account_no_write(self):
        with patch('zodiac_instagram._account_key',return_value='wrong'), patch('zodiac_instagram.publish_reel') as send:
            with self.assertRaises(RuntimeError):z.publish('ig_short',DAY,self.gh,True,NOW)
            send.assert_not_called();self.assertEqual(self.gh.writes,[])
    def test_threads_configured_id_mismatch_no_write(self):
        with patch.dict(os.environ,{'THREADS_USER_ID':'different'}):
            with self.assertRaises(RuntimeError):self.run_publish()
        self.send.assert_not_called();self.assertEqual(self.gh.writes,[])
    def test_dispatch_auth_fail_closed(self):
        env={'ZODIAC_TWO_SLOT_LIVE':'1','GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'workflow_dispatch'}
        self.assertFalse(z.live_authorized(env,'ig_short'))
        self.assertTrue(z.live_authorized({**env,'ZODIAC_LOCAL_DISPATCH':'1'},'ig_short'))
        self.assertFalse(z.live_authorized({**env,'ZODIAC_LOCAL_DISPATCH':'1'},'threads_short'))
        self.assertFalse(z.live_authorized({**env,'ZODIAC_LOCAL_DISPATCH':'1','GITHUB_REF':'refs/heads/other'},'ig_short'))
        self.assertFalse(z.live_authorized({**env,'ZODIAC_LOCAL_DISPATCH':'1','ZODIAC_TWO_SLOT_LIVE':'0'},'ig_short'))
        self.assertTrue(z.live_authorized({**env,'GITHUB_EVENT_NAME':'schedule'},'threads_short'))
if __name__=='__main__':unittest.main()
