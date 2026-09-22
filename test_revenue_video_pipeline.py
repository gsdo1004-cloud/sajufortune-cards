import unittest
import revenue_video_pipeline as r
class T(unittest.TestCase):
 def test_script_original_structure(self): self.assertGreaterEqual(len(r.script('2026-09-23')),6)
 def test_isolated_paths(self): self.assertEqual(r.OUT.name,'reels_revenue'); self.assertEqual(r.CARDROOT.name,'revenue_cards')
 def test_no_guarantee_language(self): self.assertNotIn('반드시 돈', ' '.join(r.script('2026-09-23')))
if __name__=='__main__': unittest.main()
