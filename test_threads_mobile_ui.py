import unittest
from datetime import datetime,timezone,timedelta
from threads_mobile_ui import UiJob,qualify,transition,verify_compose,verify_receipt
class MobileUiTests(unittest.TestCase):
 def job(self,**kw):
  d=dict(target_id='1',username='acct',post_text='사주 재물운',published_at=datetime.now(timezone.utc).isoformat(),comment='재물운은 시기 흐름을 함께 보면 더 입체적으로 보이네요.')
  d.update(kw); return UiJob(**d)
 def test_recent_ok(self): self.assertEqual(qualify(self.job()),(True,'ok'))
 def test_stale_blocked(self): self.assertEqual(qualify(self.job(published_at=(datetime.now(timezone.utc)-timedelta(hours=37)).isoformat()))[1],'stale')
 def test_promo_blocked(self): self.assertEqual(qualify(self.job(comment='자세한 내용은 https://example.com 에서 확인하세요'))[1],'promotional')
 def test_exact_compose(self): self.assertTrue(verify_compose('한글 댓글','한글 댓글')); self.assertFalse(verify_compose('한글댓글','한글 댓글'))
 def test_receipt_requires_account_and_text(self): self.assertTrue(verify_receipt('gsdo10042026\n정확한 댓글','gsdo10042026','정확한 댓글'))
 def test_unverified_terminal(self):
  j=self.job(); transition(j,'READY_UI'); transition(j,'OPENED'); transition(j,'COMPOSED'); transition(j,'SUBMITTED'); transition(j,'FAILED_UNVERIFIED')
  with self.assertRaises(ValueError): transition(j,'READY_UI')
if __name__=='__main__': unittest.main()
