import unittest
from pathlib import Path
import revenue_video_pipeline as r
class VoicePolicy(unittest.TestCase):
 def test_bline_policy(self):
  src=Path(r.__file__).read_text(encoding='utf-8')
  self.assertIn("REVENUE_SUPERTONIC_VOICE', 'F3'",src)
  self.assertIn("'tts_fallback':'Edge TTS'",src)
 def test_a_runtime_unchanged_m2(self):
  # Assert the versioned A-line workflow, not a machine-specific live checkout.
  p=Path(__file__).resolve().parent/'.github'/'workflows'/'zodiac-cards.yml'
  self.assertIn('SUPERTONIC_VOICE: "M2"',p.read_text(encoding='utf-8'))
if __name__=='__main__': unittest.main()
