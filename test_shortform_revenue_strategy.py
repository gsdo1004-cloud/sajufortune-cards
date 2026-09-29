import unittest
from shortform_revenue_strategy import caption, validate_reward_video, instagram_fortune_cta

class T(unittest.TestCase):
 def test_reward_gate(self):
  self.assertFalse(validate_reward_video(59)[0]); self.assertTrue(validate_reward_video(70)[0])

 def test_caption_search(self):
  self.assertIn('#오늘의운세',caption('2026-09-22'))

 def test_sparse_site_cta_tiktok(self):
  xs=[caption(f'2026-09-{d:02d}','tiktok') for d in range(20,25)]
  self.assertEqual(sum('sajufortune.kr' in x for x in xs),1)

 def test_instagram_campaign_days(self):
  # 2026-09-29 Tue, 10-01 Thu, 10-04 Sun
  self.assertTrue(instagram_fortune_cta('2026-09-29'))
  self.assertTrue(instagram_fortune_cta('2026-10-01'))
  self.assertTrue(instagram_fortune_cta('2026-10-04'))
  self.assertEqual(instagram_fortune_cta('2026-09-30'),'')

 def test_instagram_public_cta_asks_keyword_only(self):
  text=caption('2026-09-29','instagram')
  self.assertIn("댓글에",text)
  self.assertIn("DM",text)
  for sensitive in ('생년월일','태어난 시간','성별'):
   self.assertNotIn(sensitive,text)

 def test_instagram_variants_change(self):
  xs={instagram_fortune_cta(d) for d in ('2026-09-29','2026-10-01','2026-10-04','2026-10-06','2026-10-08')}
  self.assertGreaterEqual(len(xs),3)

if __name__=='__main__':
 unittest.main()
