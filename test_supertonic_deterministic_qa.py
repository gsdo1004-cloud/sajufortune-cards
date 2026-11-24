"""Offline-only deterministic Supertonic; no external TTS or publishing."""
from __future__ import annotations
import shutil
import numpy as np
import tts_supertonic as st


class FakeEngine:
    def get_voice_style(self, voice_name):
        return object()
    def synthesize(self,text,voice_style,lang,total_steps,speed):
        assert lang=="ko"
        return np.random.randn(1,1024).astype(np.float32), None
    def save_audio(self,wav,path):
        with open(path,"wb") as f: f.write(wav.tobytes())


def fake_setup(monkeypatch):
    monkeypatch.setattr(st,"_engine",lambda:FakeEngine())
    monkeypatch.setattr(st,"_FAILED",False)
    def run(cmd,**kwargs):
        shutil.copyfile(cmd[cmd.index("-i")+1],cmd[-1])
        return object()
    monkeypatch.setattr(st.subprocess,"run",run)


def test_seeded_audio_repeats(tmp_path,monkeypatch):
    fake_setup(monkeypatch)
    monkeypatch.setenv("SUPERTONIC_DETERMINISTIC_QA","1")
    p=tmp_path/"a.mp3";q=tmp_path/"b.mp3"
    assert st.synth("동일한 문장과 목소리.",p,speed=1.2)
    assert st.synth("동일한 문장과 목소리.",q,speed=1.2)
    assert p.read_bytes()==q.read_bytes()


def test_seed_identity_changes_with_text_voice(tmp_path,monkeypatch):
    fake_setup(monkeypatch)
    monkeypatch.setenv("SUPERTONIC_DETERMINISTIC_QA","1")
    monkeypatch.setattr(st,"VOICE","M2")
    p=tmp_path/"a.mp3";q=tmp_path/"b.mp3";r=tmp_path/"c.mp3"
    assert st.synth("다른 문장 A",p)
    assert st.synth("다른 문장 B",q)
    monkeypatch.setattr(st,"VOICE","F2")
    assert st.synth("다른 문장 A",r)
    assert len({p.read_bytes(),q.read_bytes(),r.read_bytes()})==3


def test_seed_restores_global_rng_state(tmp_path,monkeypatch):
    fake_setup(monkeypatch)
    monkeypatch.setenv("SUPERTONIC_DETERMINISTIC_QA","1")
    np.random.seed(123)
    initial=np.random.get_state()
    assert st.synth("난수 복원",tmp_path/"a.mp3")
    final=np.random.get_state()
    assert initial[0]==final[0] and np.array_equal(initial[1],final[1])
    assert initial[2:]==final[2:]


def test_default_unseeded_unchanged(tmp_path,monkeypatch):
    fake_setup(monkeypatch)
    monkeypatch.delenv("SUPERTONIC_DETERMINISTIC_QA",raising=False)
    np.random.seed(123)
    p=tmp_path/"a.mp3";q=tmp_path/"b.mp3"
    assert st.synth("기존 동작",p)
    assert st.synth("기존 동작",q)
    assert p.read_bytes()!=q.read_bytes()
