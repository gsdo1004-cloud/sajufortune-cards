"""Scheduled 7-style generation must require Hanbok with no legacy drift.

No network, workflow dispatch, secret access or content upload.
"""
import json
import subprocess
import sys
from pathlib import Path
import pytest
from scripts import zodiac_workflow_avatar_env as wa

DAY='2026-12-07'

def put(root, fragment, payload):
    p=root / fragment
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(payload),encoding='utf-8')
    return p

def test_legacy_no_source_does_not_enable_strict(tmp_path):
    assert wa.mode(DAY,tmp_path)=='LEGACY'

def test_legacy_manifest_without_style_id_remains_legacy(tmp_path):
    put(tmp_path,f'assets/flux_daily/{DAY}/manifest.json',{'schema':1})
    assert wa.mode(DAY,tmp_path)=='LEGACY'

def test_styled_source_enables_strict_without_claiming_approval(tmp_path):
    put(tmp_path,f'assets/flux_daily/{DAY}/manifest.json',{'style_id':'STYLE_06','status':'PENDING_QA'})
    assert wa.mode(DAY,tmp_path)=='STYLED'

def test_styled_layout_and_manifest_match(tmp_path):
    put(tmp_path,f'assets/flux_daily/{DAY}/manifest.json',{'style_id':'STYLE_05'})
    put(tmp_path,f'cards/{DAY}/layout_manifest.json',{'style_id':'STYLE_05'})
    assert wa.mode(DAY,tmp_path)=='STYLED'

def test_style_removed_from_manifest_blocks_downgrade(tmp_path):
    put(tmp_path,f'assets/flux_daily/{DAY}/manifest.json',{'schema':1})
    put(tmp_path,f'cards/{DAY}/layout_manifest.json',{'style_id':'STYLE_02'})
    with pytest.raises(wa.WorkflowHold,match='STYLED_LAYOUT_WITHOUT_ATLAS_MANIFEST'):
        wa.mode(DAY,tmp_path)

def test_style_layout_without_manifest_blocks_downgrade(tmp_path):
    put(tmp_path,f'cards/{DAY}/layout_manifest.json',{'style_id':'STYLE_02'})
    with pytest.raises(wa.WorkflowHold,match='STYLED_LAYOUT_WITHOUT_ATLAS_MANIFEST'):
        wa.mode(DAY,tmp_path)

def test_mismatch_blocks(tmp_path):
    put(tmp_path,f'assets/flux_daily/{DAY}/manifest.json',{'style_id':'STYLE_04'})
    put(tmp_path,f'cards/{DAY}/layout_manifest.json',{'style_id':'STYLE_05'})
    with pytest.raises(wa.WorkflowHold,match='STYLED_LAYOUT_STYLE_MISMATCH'):
        wa.mode(DAY,tmp_path)

def test_unsupported_style_blocks(tmp_path):
    put(tmp_path,f'assets/flux_daily/{DAY}/manifest.json',{'style_id':'STYLE_98'})
    with pytest.raises(wa.WorkflowHold,match='UNRECOGNIZED_STYLE_ID'):
        wa.mode(DAY,tmp_path)

def test_manifest_shell_injection_cannot_pass(tmp_path):
    put(tmp_path,f'assets/flux_daily/{DAY}/manifest.json',{'style_id':'STYLE_06;$(touch /tmp/nope)'})
    with pytest.raises(wa.WorkflowHold,match='UNRECOGNIZED_STYLE_ID'):
        wa.mode(DAY,tmp_path)

def test_invalid_json_fails_closed(tmp_path):
    p=tmp_path/f'assets/flux_daily/{DAY}/manifest.json'
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text('{bad',encoding='utf-8')
    with pytest.raises(wa.WorkflowHold,match='STYLED_METADATA_MISSING_OR_INVALID'):
        wa.mode(DAY,tmp_path)

def test_invalid_date_blocks(tmp_path):
    with pytest.raises(wa.WorkflowHold,match='INVALID_ISO_DATE'):
        wa.mode('2026-02-30',tmp_path)

def test_schedule_has_explicit_strict_styled_flags_and_signed_guard():
    text=(wa.ROOT/'.github/workflows/zodiac-cards.yml').read_text(encoding='utf-8')
    assert 'AVATAR_MODE=$(python scripts/zodiac_workflow_avatar_env.py "$TARGET") || exit 1' in text
    assert 'ZODIAC_ALLOW_HUMAN_PIP=1' in text
    assert 'ZODIAC_REQUIRE_HANBOK_AVATAR=1' in text
    assert 'ZODIAC_AVATAR: "1"' in text
    assert 'SUPERTONIC_VOICE: "M2"' in text
    assert 'python scripts/zodiac_publish_guard.py video' in text
    assert text.index('release preflight (no publish)') < text.index('커밋 (카드+릴스 public raw 호스팅)')

def test_selector_cli_only_emits_fixed_modes_and_avoids_user_values(tmp_path):
    proc=subprocess.run([sys.executable,str(wa.ROOT/'scripts/zodiac_workflow_avatar_env.py'),DAY],
                        cwd=wa.ROOT, capture_output=True,text=True,timeout=10)
    assert proc.returncode==0
    assert proc.stdout.strip() in {'STYLED','LEGACY'}
    assert proc.stderr==''
