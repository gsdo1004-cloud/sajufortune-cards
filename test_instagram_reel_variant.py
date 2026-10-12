from pathlib import Path

import instagram_reel_variant as irv


def test_variant_output_names_are_distinct():
    assert irv.output_path(Path('reels/2026-10-14_tts.mp4'), 'A').name == '2026-10-14_tts_ig_A.mp4'
    assert irv.output_path(Path('reels/2026-10-14_tts.mp4'), 'B').name == '2026-10-14_tts_ig_B.mp4'


def test_hook_text_matches_experiment_variants():
    assert irv.hook_text('A') != irv.hook_text('B')
    assert '띠' in irv.hook_text('A')
    assert '띠' in irv.hook_text('B')
