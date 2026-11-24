#!/usr/bin/env python3
"""Synthetic transition/failure/restart tests for the completion handoff.

Every external boundary (the two exact benchmark tools and the board CLI) is
replaced by a local stub so tests never touch the live controller, run a MiCall
job, or post to the real board. The production code path is otherwise unchanged.
"""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.p0_completion_handoff import watcher as W  # noqa: E402

AUDIT_SCRIPT = """#!/usr/bin/env python3
import sys, json, os
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index('--out') + 1])
root = Path(__file__).resolve().parent
with (root / 'invocations.log').open('a') as fh: fh.write('audit\\n')
doc = json.loads(os.environ['STUB_AUDIT_JSON'])
out.write_text(json.dumps(doc))
print('AUDIT_SCOPE COMPLETE_COHORT_DIAGNOSTIC_NOT_QUALIFICATION attested 198 198')
"""

DECISION_SCRIPT = """#!/usr/bin/env python3
import sys, json, os
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index('--out') + 1])
root = Path(__file__).resolve().parent
with (root / 'invocations.log').open('a') as fh: fh.write('decision\\n')
doc = json.loads(os.environ['STUB_DECISION_JSON'])
out.write_text(json.dumps(doc))
print('P0_FINAL_DECISION', doc['decision'])
"""

BOARD_SCRIPT = """#!/usr/bin/env python3
import sys, os
from pathlib import Path
args = sys.argv[1:]
i = args.index('--body')
body = args[i + 1]
issue = args[args.index('--id') + 1]
fail_file = os.environ.get('FAIL_FILE')
if fail_file and Path(fail_file).exists():
    n = int(Path(fail_file).read_text())
    if n > 0:
        Path(fail_file).write_text(str(n - 1))
        sys.stderr.write('simulated board outage\\n')
        sys.exit(7)
log = Path(os.environ['BOARD_LOG'])
with log.open('a') as fh:
    fh.write('=== ' + issue + ' ===\\n' + body + '\\n')
print('{"ok":true}')
"""

HEALTH = {
    "schema": W.HEALTH_SCHEMA,
    "state": "RUNNING_SOURCE_FROZEN_P0",
    "completed": 153,
    "total": 198,
    "utc": "2026-11-24T04:43:11Z",
}


def audit_doc(attested=198):
    return {
        "schema": W.AUDIT_SCHEMA,
        "attested_finished_cases": attested,
        "expected_cases": 198,
        "qualification_claim": "NONE",
        "pinned": {"image_sha256": W.PINNED_IMAGE,
                   "manifest_sha256": W.PINNED_MANIFEST,
                   "panel_sha256": W.PINNED_PANEL},
        "status": "COMPLETE_COHORT_DIAGNOSTIC_NOT_QUALIFICATION",
        "comparators": {},
    }


def decision_doc(decision="PHYSICAL_FULL_SEVEN_ALL_R_PASS_NO_EXPANDED_CLAIM",
                 contains_ids=False):
    return {
        "schema": W.DECISION_SCHEMA,
        "decision": decision,
        "qualification_claim": "NONE",
        "expanded_claim": "NONE",
        "contains_sample_identifiers": contains_ids,
        "cohort": {"attested_finished_cases": 198, "expected_cases": 198, "complete": True},
        "decision_scope": "PHYSICAL_ORIGINAL_198_ONLY",
    }


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bench = self.root / "src" / "benchmarks"
        self.bench.mkdir(parents=True)
        (self.bench / "independent_frozen_psi_audit.py").write_text(AUDIT_SCRIPT)
        (self.bench / "final_p0_decision.py").write_text(DECISION_SCRIPT)
        (self.bench / "invocations.log").write_text("")
        self.board_log = self.root / "board.log"
        self.board_log.write_text("")
        self.fail_file = self.root / "fail.count"
        self.artifacts = self.root / "artifacts"
        self.health_path = self.root / "health.json"
        self.write_health(HEALTH)

        env_patch = mock.patch.dict(os.environ, {
            "STUB_AUDIT_JSON": json.dumps(audit_doc()),
            "STUB_DECISION_JSON": json.dumps(decision_doc()),
            "BOARD_LOG": str(self.board_log),
            "FAIL_FILE": str(self.fail_file),
        })
        env_patch.start()
        self.addCleanup(env_patch.stop)
        sleep_patch = mock.patch.object(W.time, "sleep", lambda _n: None)
        sleep_patch.start()
        self.addCleanup(sleep_patch.stop)

    def write_health(self, doc):
        self.health_path.write_text(json.dumps(doc))

    def config(self):
        return {
            "python": sys.executable,
            "source_root": str(self.root / "src"),
            "audited_root": str(self.root / "audited"),
            "frozen_root": str(self.root / "frozen"),
            "projects_json": str(self.root / "projects.json"),
            "hxb2_fasta": str(self.root / "hxb2.fasta"),
            "artifacts_dir": str(self.artifacts),
            "health": str(self.health_path),
            "owner": "agent-W828YF4l6XKNvnCtjHdrZy-sparkled",
            "repository": "https://github.com/ottojung/ivanka",
            "source_commit": "testcommit",
            "board_command": [sys.executable, str(self.root / "fake_board.py")],
            "board_issues": ["h4u6MKP9T9prsOqr3ZULCZ-liver"],
            "interval": 0,
            "max_attempts": 3,
            "exit_when_done": True,
        }

    def finish_board_script(self):
        (self.root / "fake_board.py").write_text(BOARD_SCRIPT)

    def invocations(self):
        return (self.bench / "invocations.log").read_text().split()


class ClassificationTests(unittest.TestCase):
    def test_all_phases(self):
        cases = [
            ("RUNNING_SOURCE_FROZEN_P0", 153, "RUNNING"),
            ("BOUNDED_BATCH_DONE", 160, "RUNNING"),
            ("PAUSED_DISK_RESERVATION", 160, "PAUSED"),
            ("FATAL_MANUAL_REVIEW_REQUIRED", 160, "FATAL"),
            ("P0_FULL_SEVEN_QUALIFIED", 198, "COMPLETE"),
            ("P0_ALL198_COMPLETE_SCIENTIFIC_GATES_FAIL_MANUAL_REVIEW", 198, "COMPLETE"),
            ("P0_FULL_SEVEN_QUALIFIED", 197, "MALFORMED"),
            ("SOMETHING_NEW", 198, "UNKNOWN"),
        ]
        for state, completed, expected in cases:
            health = dict(HEALTH, state=state, completed=completed)
            with self.subTest(state=state, completed=completed):
                self.assertEqual(W.classify(health)[0], expected)
        self.assertEqual(W.classify({"schema": "wrong"})[0], "MALFORMED")
        self.assertEqual(W.classify(None)[0], "MALFORMED")


class HandoffTests(Harness):
    def test_complete_produces_hash_attested_artifacts_and_one_board_post(self):
        self.finish_board_script()
        self.write_health(dict(HEALTH, state="P0_FULL_SEVEN_QUALIFIED", completed=198,
                               final_all_r_sha256="abc123", utc="2026-11-24T05:00:00Z"))
        self.assertEqual(W.run(self.config(), max_polls=1), 0)
        self.assertEqual(self.invocations(), ["audit", "decision"])
        manifest = json.loads((self.artifacts / "manifest.json").read_text())
        self.assertEqual(manifest["decision"]["state"],
                         "PHYSICAL_FULL_SEVEN_ALL_R_PASS_NO_EXPANDED_CLAIM")
        self.assertEqual(manifest["attested_finished_cases"], 198)
        for key in ("readback", "decision"):
            entry = manifest[key]
            path = self.artifacts / entry["name"]
            self.assertEqual(W.sha256_file(path), entry["sha256"])
        body = self.board_log.read_text()
        self.assertIn("[p0-completion-handoff]", body)
        self.assertIn("final_decision: PHYSICAL_FULL_SEVEN_ALL_R_PASS_NO_EXPANDED_CLAIM", body)
        self.assertIn("expanded_claim: NONE", body)
        self.assertIn("next: 1) independent reviewer", body)
        self.assertEqual(body.count("[p0-completion-handoff]"), 1)

    def test_restart_does_not_rescore_or_repost(self):
        self.finish_board_script()
        self.write_health(dict(HEALTH, state="P0_FULL_SEVEN_QUALIFIED", completed=198,
                               final_all_r_sha256="abc123"))
        cfg = self.config()
        W.run(cfg, max_polls=1)
        first = self.invocations()
        first_posts = self.board_log.read_text().count("[p0-completion-handoff]")
        W.run(cfg, max_polls=1)
        self.assertEqual(self.invocations(), first)
        self.assertEqual(self.board_log.read_text().count("[p0-completion-handoff]"), first_posts)

    def test_manifest_survives_journal_loss(self):
        self.finish_board_script()
        self.write_health(dict(HEALTH, state="P0_FULL_SEVEN_QUALIFIED", completed=198,
                               final_all_r_sha256="abc123"))
        cfg = self.config()
        W.run(cfg, max_polls=1)
        (self.artifacts / "journal.json").unlink()
        W.run(cfg, max_polls=1)
        self.assertEqual(len(self.invocations()), 2)
        self.assertEqual(self.board_log.read_text().count("[p0-completion-handoff]"), 1)

    def test_tampered_artifact_forces_represervation(self):
        self.finish_board_script()
        self.write_health(dict(HEALTH, state="P0_FULL_SEVEN_QUALIFIED", completed=198,
                               final_all_r_sha256="abc123"))
        cfg = self.config()
        W.run(cfg, max_polls=1)
        (self.artifacts / "readback-audit-198.json").write_text("tampered")
        (self.artifacts / "journal.json").unlink()
        W.run(cfg, max_polls=1)
        self.assertEqual(len(self.invocations()), 4)

    def test_fatal_path_notifies_without_scoring(self):
        self.finish_board_script()
        self.write_health(dict(HEALTH, state="FATAL_MANUAL_REVIEW_REQUIRED",
                               error="RuntimeError('disk')", utc="2026-11-24T06:00:00Z"))
        W.run(self.config(), max_polls=1)
        self.assertEqual(self.invocations(), [])
        self.assertEqual(len(list(self.artifacts.glob("fatal-*.json"))), 1)
        body = self.board_log.read_text()
        self.assertIn("state: CONTROLLER_FATAL", body)
        self.assertIn("do NOT blindly restart", body)

    def test_paused_is_not_finished(self):
        self.finish_board_script()
        self.write_health(dict(HEALTH, state="PAUSED_DISK_RESERVATION", completed=160))
        cfg = self.config()
        cfg["exit_when_done"] = False
        W.run(cfg, max_polls=1)
        self.assertEqual(self.invocations(), [])
        self.assertEqual(self.board_log.read_text(), "")
        journal = json.loads((self.artifacts / "journal.json").read_text())
        self.assertEqual(journal["last_phase"], "PAUSED")

    def test_integrity_failure_is_fail_closed(self):
        self.finish_board_script()
        os.environ["STUB_AUDIT_JSON"] = json.dumps(audit_doc(attested=150))
        self.write_health(dict(HEALTH, state="P0_FULL_SEVEN_QUALIFIED", completed=198,
                               final_all_r_sha256="abc123"))
        W.run(self.config(), max_polls=1)
        self.assertEqual(self.invocations(), ["audit"])
        body = self.board_log.read_text()
        self.assertIn("final_decision: INTEGRITY_FAILURE", body)
        self.assertIn("audit_not_198_attested", body)

    def test_board_outage_retries_then_succeeds(self):
        self.finish_board_script()
        self.fail_file.write_text("2")
        self.write_health(dict(HEALTH, state="P0_FULL_SEVEN_QUALIFIED", completed=198,
                               final_all_r_sha256="abc123"))
        cfg = self.config()
        cfg["exit_when_done"] = False
        W.run(cfg, max_polls=1)
        self.assertEqual(self.invocations(), ["audit", "decision"])
        self.assertEqual(self.board_log.read_text().count("[p0-completion-handoff]"), 1)
        manifest = json.loads((self.artifacts / "manifest.json").read_text())
        self.assertEqual(len(manifest["board_notification"]), 1)

    def test_board_outage_exhausts_without_looping(self):
        self.finish_board_script()
        self.fail_file.write_text("99")
        self.write_health(dict(HEALTH, state="P0_FULL_SEVEN_QUALIFIED", completed=198,
                               final_all_r_sha256="abc123"))
        cfg = self.config()
        cfg["exit_when_done"] = False
        cfg["max_attempts"] = 1
        W.run(cfg, max_polls=1)
        journal = json.loads((self.artifacts / "journal.json").read_text())
        entry = next(iter(journal["handled"].values()))
        self.assertTrue(entry["done"])
        self.assertEqual(entry["outcome"], "board_post_exhausted")
        self.assertEqual(self.board_log.read_text(), "")

    def test_decision_with_identifiers_rejected(self):
        self.assertIn("decision_may_contain_sample_identifiers",
                      W.validate_decision(decision_doc(contains_ids=True)))

    def test_validate_audit_rejects_hash_drift(self):
        doc = audit_doc()
        doc["pinned"]["image_sha256"] = "deadbeef"
        self.assertIn("audit_image_hash_mismatch", W.validate_audit(doc))


if __name__ == "__main__":
    unittest.main(verbosity=2)
