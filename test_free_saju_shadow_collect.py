import os,unittest
from free_saju_shadow_collect import record,keyword
class T(unittest.TestCase):
 def test_keyword(self): self.assertEqual(keyword("재물운 궁금"),"재물")
 def test_artifact_has_no_raw_pii(self):
  x=record("instagram","123","1990.03.12 생년월일 사주","2026-10-03T00:00:00Z")
  for k in ("text","username","comment_id","id","birth_date"): self.assertNotIn(k,x)
  self.assertTrue(x["qualified"]);self.assertFalse(x["parser_success"]);self.assertFalse(x["engine_success"])
  self.assertNotEqual(x["source_id_hash"],"123")
if __name__=="__main__":unittest.main()
