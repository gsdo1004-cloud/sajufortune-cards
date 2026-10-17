from pathlib import Path

WORKFLOW = Path('.github/workflows/instagram-revenue.yml').read_text(encoding='utf-8')


def step_block(name: str) -> str:
    marker = f'- name: {name}'
    start = WORKFLOW.index(marker)
    rest = WORKFLOW[start:]
    next_pos = rest.find('\n      - name:', len(marker))
    return rest if next_pos < 0 else rest[:next_pos]


def test_scheduled_legacy_reel_runs_even_if_primary_failed():
    block = step_block('Publish scheduled Legacy Reel')
    assert "if: always() && github.event_name == 'schedule' && steps.target.outputs.mode == 'reel'" in block


def test_legacy_insights_run_after_prior_step_failure():
    block = step_block('Collect Legacy aggregate insights')
    assert 'if: always() && (' in block


def test_state_persist_runs_after_one_account_failure():
    block = step_block('Persist idempotency markers and aggregate insights')
    assert 'if: always() && (' in block
