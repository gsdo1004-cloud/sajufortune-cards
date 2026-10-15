from pathlib import Path


WORKFLOW = Path(__file__).parent / ".github" / "workflows" / "instagram-revenue.yml"


def text():
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_supports_legacy_account_credentials_and_manual_selection():
    s = text()
    assert "INSTAGRAM_LEGACY_USER_ID" in s
    assert "INSTAGRAM_LEGACY_ACCESS_TOKEN" in s
    assert "INSTAGRAM_ACCOUNT_KEY: sajufortune.kr" in s
    assert "INSTAGRAM_EXPECTED_USERNAME: sajufortune.kr" in s
    assert "account:" in s
    assert "primary | legacy | both" in s


def test_scheduled_reel_publishes_legacy_but_afternoon_content_does_not():
    s = text()
    assert "Publish scheduled Legacy Reel" in s
    assert "steps.target.outputs.mode == 'reel'" in s
    assert "INSTAGRAM_EXPERIMENT_VARIANT: ${{ steps.variants.outputs.legacy_variant }}" in s


def test_manual_status_does_not_persist_state():
    s = text()
    assert "github.event_name == 'schedule' || github.event.inputs.publish == 'true'" in s


def test_checkout_is_shallow_partial_sparse_and_keeps_only_instagram_state():
    s = text()
    assert "fetch-depth: 1" in s
    assert "sparse-checkout-cone-mode: false" in s
    assert "/*\n            !/*/\n            /scripts/\n            /analytics/\n            /cards/*/instagram_pub_*.json" in s
    assert "fetch-depth: 0" not in s
