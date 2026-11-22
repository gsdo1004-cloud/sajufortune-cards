"""PR25 isolated, no-network tests for strict same-day concurrency and existing publish receipt protection."""
import json
import threading
import pytest
import zodiac_reels as reel


@pytest.fixture
def scope(tmp_path,monkeypatch):
 folder=tmp_path/'cards'/'2026-12-07'
 folder.mkdir(parents=True)
 monkeypatch.setattr(reel,'BASE',tmp_path)
 monkeypatch.setenv('ZODIAC_REQUIRE_HANBOK_AVATAR','1')
 return folder


def test_preexisting_publication_receipt_blocks_before_generator(scope,monkeypatch):
 marker=scope/'youtube_pub.json'
 marker.write_bytes(b'{"uploaded": true, "id": "historic"}')
 before=marker.read_bytes()
 monkeypatch.setattr(reel,'_make_reel_tts_impl',
  lambda *args: (_ for _ in ()).throw(AssertionError("MUST_NOT_RUN")))
 with pytest.raises(RuntimeError,match='STRICT_ZODIAC_PUBLISHED_RECEIPT_PROTECTED'):
  reel.make_reel_tts('2026-12-07')
 assert marker.read_bytes()==before
 assert not (scope/'.pr25_hanbok_render.lock').exists()


def test_preexisting_lock_blocks_concurrent_worker(scope,monkeypatch):
 lock=scope/'.pr25_hanbok_render.lock'
 lock.write_text(json.dumps({'token':'other','pid':77}))
 monkeypatch.setattr(reel,'_make_reel_tts_impl',
  lambda *args: (_ for _ in ()).throw(AssertionError("MUST_NOT_RUN")))
 with pytest.raises(RuntimeError,match='STRICT_ZODIAC_CONCURRENT_RENDER_BLOCKED'):
  reel.make_reel_tts('2026-12-07')
 assert lock.exists() and json.loads(lock.read_text())['token']=='other'


def test_strict_success_recovers_own_lock(scope,monkeypatch):
 def routine(*args):
  lock=scope/'.pr25_hanbok_render.lock'
  assert lock.exists()
  record=json.loads(lock.read_text())
  assert record['date']=='2026-12-07' and record['pid']>0 and len(record['token'])==32
  return 'TEST_ONLY_OK'
 monkeypatch.setattr(reel,'_make_reel_tts_impl',routine)
 assert reel.make_reel_tts('2026-12-07')=='TEST_ONLY_OK'
 assert not (scope/'.pr25_hanbok_render.lock').exists()


def test_generator_failure_still_cleans_own_lock(scope,monkeypatch):
 def fail(*args):raise RuntimeError('OFFLINE_SYNTH_FAIL')
 monkeypatch.setattr(reel,'_make_reel_tts_impl',fail)
 with pytest.raises(RuntimeError,match='OFFLINE_SYNTH_FAIL'):
  reel.make_reel_tts('2026-12-07')
 assert not (scope/'.pr25_hanbok_render.lock').exists()


def test_simultaneous_two_calls_second_fails_closed(scope,monkeypatch):
 entered=threading.Event()
 release=threading.Event()
 result=[]
 def inner(*args):
  entered.set()
  assert release.wait(5)
  return 'OK'
 monkeypatch.setattr(reel,'_make_reel_tts_impl',inner)
 def first():
  try:result.append(reel.make_reel_tts('2026-12-07'))
  except Exception as e:result.append(repr(e))
 worker=threading.Thread(target=first)
 worker.start()
 assert entered.wait(2)
 with pytest.raises(RuntimeError,match='STRICT_ZODIAC_CONCURRENT_RENDER_BLOCKED'):
  reel.make_reel_tts('2026-12-07')
 release.set()
 worker.join(4)
 assert result==['OK']
 assert not (scope/'.pr25_hanbok_render.lock').exists()


def test_legacy_default_has_no_new_qa_lock(scope,monkeypatch):
 monkeypatch.delenv('ZODIAC_REQUIRE_HANBOK_AVATAR',raising=False)
 (scope/'uploaded.json').write_text('{"existing": true}')
 monkeypatch.setattr(reel,'_make_reel_tts_impl',lambda *args:'LEGACY_UNCHANGED')
 assert reel.make_reel_tts('2026-12-07')=='LEGACY_UNCHANGED'
 assert not (scope/'.pr25_hanbok_render.lock').exists()
