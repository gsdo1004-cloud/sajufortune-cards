"""No-cost contract tests for all twelve Korean zodiac visual formats."""
import datetime as dt
import unittest

import zodiac_visual_rotation as zvr
import zodiac_prompt_engine as engine

class VisualRotationContract(unittest.TestCase):
    def test_eight_unique_styles_and_no_adjacent_repeat(self):
        start = dt.date(2026, 11, 12)
        selected = [zvr.style_for(start + dt.timedelta(days=i))["id"] for i in range(28)]
        self.assertEqual(len(set(selected)), 8)
        self.assertTrue(all(a != b for a,b in zip(selected,selected[1:])))

    def test_exact_twelve_signs_and_cultural_guards(self):
        self.assertEqual(len(engine.ZODIAC12), 12)
        self.assertEqual(len(set(engine.ZODIAC12)), 12)
        self.assertIn("no wings", engine.ZODIAC_FEATURES["용띠"])
        self.assertIn("no snake fangs", engine.ZODIAC_NEGATIVE_PROMPT)
        self.assertIn("no generic korean hanbok woman", zvr.ANIMAL_GUARD.lower())

    def test_all_prompts_follow_date_style_without_woman_presenter(self):
        d = dt.date(2026, 11, 14)
        rows = {s: {"line": "차분한 하루를 보내세요", "advice": "신중하게 선택하세요", "lucky": "동쪽",
                    "stars":{"전체":4,"금전":3,"연애":4,"건강":4}}
                for s in engine.ZODIAC12}
        pack=engine.daily_set(d,rows)
        self.assertEqual(len(pack["images"]),4)
        self.assertEqual(pack["theme"]["visual_id"],zvr.style_for(d)["id"])
        for image in pack["images"]:
            for field in ("prompt","simple_prompt"):
                self.assertIn(zvr.style_for(d)["prompt"],image[field])
                self.assertNotIn("A beautiful Korean woman wearing",image[field])

    def test_monthly_card_groups_preserve_all_signs(self):
        import zodiac_month_topview as monthly
        pack=monthly.month_set(2026,12)
        self.assertEqual(len(pack["images"]),6)
        signs=[sign for item in pack["images"][1:5] for sign in item["signs"]]
        self.assertEqual(signs,engine.ZODIAC12)

    def test_html_and_signal_share_rotation(self):
        import zodiac_cardnews as html_card
        import zodiac_signal_card as signal_card
        text=html_card.build_html('2026-11-13')
        self.assertIn('border:5px solid',text)
        prompt=signal_card._prompt('용띠','재물운','오늘은 신중하게',1,simple=False,date_iso='2026-11-13')
        self.assertIn(zvr.style_for('2026-11-13')['prompt'],prompt)

if __name__=='__main__':unittest.main()
