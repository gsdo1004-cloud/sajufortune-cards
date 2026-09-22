import pathlib,unittest
class T(unittest.TestCase):
 def test_isolated(self):
  s=pathlib.Path('tiktok_longform_renderer.py').read_text(encoding='utf-8'); self.assertIn("youtube_touched':False",s); self.assertNotIn('make_reel_tts(',s)
 def test_gate(self):
  s=pathlib.Path('tiktok_longform_renderer.py').read_text(encoding='utf-8'); self.assertIn('360<=sec<=540',s)
 def test_avatar_plan(self):
  import tiktok_longform_revenue as m; p=m.plan('2026-09-23'); self.assertEqual(p['pngtuber'],'existing young male/female'); self.assertFalse(p['youtube'])
unittest.main()
