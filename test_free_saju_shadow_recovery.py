import json,os,sys,types,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import free_saju_shadow_collect as c

class RecoveryTests(unittest.TestCase):
    def test_sanitized_error(self):
        self.assertEqual(c.safe_reason(RuntimeError("secret_credential; code=190 Session has expired")),"auth_expired")
    def test_partial_preserves_threads(self):
        with TemporaryDirectory() as t:
            with patch.object(c,"OUT",Path(t)/"out.json"),patch.object(sys,"argv",["cmd","--channel","all"]),patch.object(c,"collect_instagram",side_effect=c.ChannelError("auth_expired")),patch.object(c,"collect_threads",return_value=[c.record("threads","123","사주")]):
                self.assertEqual(c.main(),0)
            x=json.loads((Path(t)/"out.json").read_text())
            self.assertEqual(x["status"],"DEGRADED")
            self.assertEqual(x["errors"],{"instagram":"auth_expired"})
            self.assertNotIn("text",x["records"][0])
    def test_full_failure_returns_nonzero(self):
        with TemporaryDirectory() as t:
            with patch.object(c,"OUT",Path(t)/"out.json"),patch.object(sys,"argv",["cmd"]),patch.object(c,"collect_instagram",side_effect=c.ChannelError("auth_expired")),patch.object(c,"collect_threads",side_effect=c.ChannelError("api_error")):
                self.assertEqual(c.main(),2)
            self.assertEqual(json.loads((Path(t)/"out.json").read_text())["status"],"FAILED")
    def test_legacy_verified_before_read_and_original_restored(self):
        calls=[]
        def profile(uid,params):
            calls.append(uid)
            if uid=="primary-id": raise RuntimeError("code=190")
            return {"username":"gsdo10042026"}
        def discover():
            self.assertEqual(os.environ["INSTAGRAM_USER_ID"],"legacy-id")
            return {},[{"comment_id":"789","text":"재물운 질문","timestamp":"2026-11-22"}]
        fake=types.SimpleNamespace(cfg=lambda:{"account_username":"gsdo10042026"},api_get=profile,discover=discover)
        env={"INSTAGRAM_ACCESS_TOKEN":"old","INSTAGRAM_USER_ID":"primary-id","INSTAGRAM_LEGACY_ACCESS_TOKEN":"good","INSTAGRAM_LEGACY_USER_ID":"legacy-id","FREE_SAJU_SHADOW_INSTAGRAM_USERNAME":"gsdo10042026"}
        with patch.dict(os.environ,env),patch.dict(sys.modules,{"instagram_comments":fake}):
            r=c.collect_instagram()
            self.assertEqual(os.environ["INSTAGRAM_USER_ID"],"primary-id")
        self.assertEqual(c.IG_SOURCE,"legacy")
        self.assertEqual(calls,["primary-id","legacy-id"])
        self.assertEqual(c.IG_AUTH_ATTEMPTS,
                         [{"source":"primary","status":"auth_expired"},
                          {"source":"legacy","status":"ok"}])
        self.assertEqual(len(r),1)

    def test_override_expected_ig_username_matches_legacy(self):
        def profile(uid, params):
            if uid=="primary-id": raise RuntimeError("code=190")
            return {"username":"sajufortune.kr"}
        def discover():
            return {}, [{"comment_id":"xx","text":"운세 질문"}]
        fake=types.SimpleNamespace(cfg=lambda:{"account_username":"gsdo10042026"},
                                   api_get=profile,discover=discover)
        env={"INSTAGRAM_ACCESS_TOKEN":"expired","INSTAGRAM_USER_ID":"primary-id",
             "INSTAGRAM_LEGACY_ACCESS_TOKEN":"valid","INSTAGRAM_LEGACY_USER_ID":"legacy-id",
             "FREE_SAJU_SHADOW_INSTAGRAM_USERNAME":"sajufortune.kr"}
        with patch.dict(os.environ,env),patch.dict(sys.modules,{"instagram_comments":fake}):
            rows=c.collect_instagram()
        self.assertEqual(c.IG_SOURCE,"legacy")
        self.assertEqual(len(rows),1)

if __name__=="__main__":unittest.main()
