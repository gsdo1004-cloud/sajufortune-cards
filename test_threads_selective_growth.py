import datetime as dt
import unittest
import threads_viral_learning as t

UTC=dt.timezone.utc

def rec(published="2026-11-20T23:00:00Z", channel="ghost", views=100, replies=4,
        arm=None, placement_verified=False, observed="2026-11-22T00:00:00Z"):
    r={"timestamp":published,"channel":channel,
       "snapshots":[{"t":observed,"age_h":24,"views":views,"replies":replies}]}
    if arm:
        r["link_placement"]=arm
        r["placement_verified"]=placement_verified
    return r

class SelectiveExperiments(unittest.TestCase):
    def test_kst_windows(self):
        self.assertEqual(t.publication_window("2026-11-20T22:00:00Z"),"morning_06_09")
        self.assertEqual(t.publication_window("2026-11-20T03:00:00Z"),"lunch_12_14")
        self.assertEqual(t.publication_window("2026-11-20T12:00:00Z"),"evening_21_24")
        self.assertEqual(t.publication_window("no time"),"unknown")

    def test_stale_evidence_blocks_optimization(self):
        old={"posts":{"x":rec(observed="2026-09-19T00:00:00Z")}}
        r=t.slot_evidence(old,now=dt.datetime(2026,11,22,tzinfo=UTC))
        self.assertEqual(r["status"],"HOLD_STALE")
        self.assertEqual(r["slots"],{})

    def test_requires_same_channel_comparisons(self):
        posts={}
        for i in range(5):
            posts[f"m{i}"]=rec(published="2026-11-21T22:00:00Z")
            posts[f"e{i}"]=rec(published="2026-11-21T12:00:00Z",channel="signal_video")
        result=t.slot_evidence({"posts":posts},now=dt.datetime(2026,11,22,12,tzinfo=UTC))
        self.assertEqual(result["status"],"HOLD_LOW_SAMPLE")

    def test_never_claims_time_winner_even_with_data(self):
        posts={}
        for i in range(5):
            posts[f"m{i}"]=rec(published="2026-11-21T22:00:00Z",views=100)
            posts[f"e{i}"]=rec(published="2026-11-21T12:00:00Z",views=200)
        result=t.slot_evidence({"posts":posts},now=dt.datetime(2026,11,22,12,tzinfo=UTC))
        self.assertEqual(result["status"],"OBSERVE_ONLY")
        self.assertEqual(result["slots"]["ghost/morning_06_09"]["n"],5)
        self.assertEqual(result["slots"]["ghost/evening_21_24"]["avg_views_24h"],200)

    def test_link_requires_verified_arm_and_verified_first_party(self):
        data={"posts":{"1":rec(arm="body"),"2":rec(arm="comment",placement_verified=True)}}
        events=[{"post_id":"1","source_verified":True,"site_sessions":9,"orders":1},
                {"post_id":"2","site_sessions":8,"orders":1}]
        out=t.link_placement_evidence(data,events,min_per_arm=1)
        self.assertEqual(out["status"],"HOLD_UNVERIFIED_ARMS")
        self.assertEqual(out["arms"]["body"]["n"],0)
        self.assertEqual(out["arms"]["comment"]["n"],0)

    def test_link_verified_both_arms_are_observation_only(self):
        data={"posts":{"1":rec(arm="body",placement_verified=True),
                       "2":rec(arm="comment",placement_verified=True)}}
        events=[{"post_id":"1","source_verified":True,"site_sessions":2,"orders":1},
                {"post_id":"2","source_verified":True,"site_sessions":1,"orders":0}]
        out=t.link_placement_evidence(data,events,min_per_arm=1)
        self.assertEqual(out["status"],"OBSERVE_ONLY")
        self.assertEqual(out["arms"]["body"]["orders"],1)

    def test_duplicate_attribution_does_not_double_count(self):
        data={"posts":{"1":rec(arm="body",placement_verified=True)}}
        event={"post_id":"1","source_verified":True,"site_sessions":1,"orders":1}
        out=t.link_placement_evidence(data,[event,event],min_per_arm=1)
        self.assertEqual(out["arms"]["body"]["orders"],0)

    def test_report_safe_when_unmeasured(self):
        out=t.selective_evidence_report({"posts":{}},[],now=dt.datetime(2026,11,22,tzinfo=UTC))
        self.assertIn("HOLD_NO_INSIGHTS",out)
        self.assertIn("HOLD_UNVERIFIED_ARMS",out)

if __name__=="__main__":
    unittest.main()
