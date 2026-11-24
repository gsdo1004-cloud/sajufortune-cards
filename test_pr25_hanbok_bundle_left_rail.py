"""Bundled original Hanbok assets must receive dedicated-rail opt-in only in strict QA mode."""
from pathlib import Path
from types import SimpleNamespace
import pytest
import avatar_pip


@pytest.mark.parametrize("use_left_rail",[True,False])
def test_avatar_pip_only_opt_in_rail(tmp_path,monkeypatch,use_left_rail):
 script=tmp_path/"run.py";script.write_text("# synthetic executable")
 frame_folder=tmp_path/"frames";frame_folder.mkdir()
 for name in avatar_pip.MOUTH_FILES:(frame_folder/name).write_bytes(b"test-alpha-frame")
 pool=tmp_path/"pool"
 monkeypatch.setattr(avatar_pip,"resolve",lambda voice=None:(script,frame_folder,pool))
 called=[]
 def subprocess_stub(cmd,**kw):
  called.append((cmd,kw))
  return SimpleNamespace(returncode=0,stdout="",stderr="")
 monkeypatch.setattr(avatar_pip.subprocess,"run",subprocess_stub)
 assert avatar_pip.apply(tmp_path/"v.mp4",voice="M2",left_rail=use_left_rail) is True
 assert len(called)==1
 if use_left_rail:
  assert called[0][1]["env"]["ZODIAC_PIP_LEFT_RAIL"]=="1"
 else:
  assert called[0][1]["env"] is None
 assert pool.exists()
