"""Zero-network regression tests: FLUX H264 without audible AAC track must HOLD."""
import json
from types import SimpleNamespace
import pytest
from scripts import visual_quality_gate as vg

@pytest.fixture
def fake_video(tmp_path,monkeypatch):
 p=tmp_path/'candidate.mp4';p.write_bytes(b'x'*120000)
 monkeypatch.setattr(vg.shutil,'which',lambda x:'/usr/bin/'+x)
 return p

@pytest.mark.parametrize('streams',[
 [{'codec_type':'video','codec_name':'h264','width':1080,'height':1920}],
 [{'codec_type':'video','codec_name':'h264','width':1080,'height':1920},{'codec_type':'audio','codec_name':'mp3'}],
 ])
def test_missing_or_wrong_audio_fail_closed(fake_video,monkeypatch,streams):
 monkeypatch.setattr(vg.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout=json.dumps({'streams':streams,'format':{'duration':'80'}})))
 with pytest.raises(vg.VisualHold,match='VIDEO_AUDIO_TRACK_MISSING_OR_NOT_AAC'):
  vg.video_check(fake_video,sample_frames=False,require_audio=True)

def test_aac_succeeds(fake_video,monkeypatch):
 streams=[{'codec_type':'video','codec_name':'h264','width':1080,'height':1920},
          {'codec_type':'audio','codec_name':'aac'}]
 monkeypatch.setattr(vg.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout=json.dumps({'streams':streams,'format':{'duration':'80'}})))
 value=vg.video_check(fake_video,sample_frames=False,require_audio=True)
 assert value['status']=='PASS'
