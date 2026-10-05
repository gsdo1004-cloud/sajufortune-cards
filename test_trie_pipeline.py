# -*- coding: utf-8 -*-
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from trie.models import load_config
from trie.pipeline import run_pipeline

NOW = datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parent


class TriePipelineTest(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()
        self.raw = json.loads((ROOT / "trie_canary_input.json").read_text(encoding="utf-8"))

    def test_synthetic_input_is_deterministic_and_recommends(self):
        mem1, rec1 = run_pipeline(self.raw, now=NOW, config=self.cfg)
        mem2, rec2 = run_pipeline(list(reversed(self.raw)), now=NOW, config=self.cfg)
        self.assertEqual(mem1, mem2)
        self.assertEqual(rec1, rec2)
        self.assertGreaterEqual(len(rec1), 1)
        self.assertEqual(mem1[0]["schema"], "trie-pattern-memory-v1")
        self.assertEqual(rec1[0]["schema"], "trie-recommendation-v1")

    def test_invalid_record_prevents_partial_pipeline_result(self):
        bad = self.raw + [{"source_type": "browser_scrape"}]
        with self.assertRaises(ValueError):
            run_pipeline(bad, now=NOW, config=self.cfg)

    def test_corrupt_cli_input_keeps_existing_outputs_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "bad.json"
            mem = td / "memory.json"
            rec = td / "recommendations.json"
            inp.write_text('{broken', encoding="utf-8")
            mem.write_bytes(b"OLD-MEMORY")
            rec.write_bytes(b"OLD-RECS")
            proc = subprocess.run([
                sys.executable, "-m", "trie.canary",
                "--input", str(inp), "--config", "trie_config.json",
                "--memory-out", str(mem), "--recommendations-out", str(rec),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(mem.read_bytes(), b"OLD-MEMORY")
            self.assertEqual(rec.read_bytes(), b"OLD-RECS")

    def test_workflow_and_pipeline_are_read_only_by_construction(self):
        workflow = (ROOT / ".github/workflows/trie-canary.yml").read_text(encoding="utf-8")
        lower = workflow.lower()
        self.assertIn("permissions:\n  contents: read", workflow)
        for forbidden in (
            "secrets.", "threads_access_token", "threads_user_id", "threads_queue_live",
            "--live", "threads_publish", "playwright", "selenium"
        ):
            self.assertNotIn(forbidden, lower)
        source = (ROOT / "trie/pipeline.py").read_text(encoding="utf-8").lower()
        for forbidden in ("import requests", "threads_growth", "threads_fortune_public", "rce_pilot_publish", "playwright", "selenium"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
