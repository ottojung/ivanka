#!/usr/bin/env python3
"""Read-only verification of the proposed PenguiN paired-pilot attestation.

No registry/receipt/STOP/lock/frozen mutation, no build, no container/pilot.
Run: python3 verify_penguin_proposal.py
"""
from pathlib import Path
import hashlib
import json
import sys
import unittest

HERE = Path(__file__).resolve().parent
REPO = Path("/workspace/px-source-readiness-20261126")
sys.path[:0] = [str(REPO), str(REPO / "benchmarks")]
from assembler_bench import exploratory_policy as pol  # noqa: E402

ROOT = Path("/workspace/ivanka-exploratory-ten-20261121")
ACTIVE_REG = ROOT / "private-frozen-ten-pilot-registry-20gib-20261124.json"
PRESERVED_REG = ROOT / "preserved/private-frozen-ten-pilot-registry-20gib-20261124.penguin-image-pinned-20261124.json"
PROPOSED_REG = HERE / "proposed-registry-penguin-pilot-20261126.json"
PROPOSED_RECEIPTS = HERE / "proposed-receipts"
PILOT = PROPOSED_RECEIPTS / "pilot-penguin-paired-canonical-proposed-20261126.json"
IMAGE = PROPOSED_RECEIPTS / "image-penguin-frozen-8458f9e5-8e7c55a3.json"

EXPECTED = {
    "active_registry": "98de47a3eb76b45d3c09b4f3aa62a299b57f67b30642c18541a062c2dc720a7a",
    "preserved_registry": "12769a2bbc4d1b97c57e63f18d4558cc7679cc7cc905c2bdd18767da1cfad890",
    "image_receipt": "5ab7651c768aa29da9346cd5fa51a89d5d14ff757fbdff23e16eefbf6e7af7c1",
    "run_physical": "55d4644a894eabb84b19e0aa51c32c91c0913c155c7ff226d4c8112601e33a0a",
    "log_physical": "0d099e830480d1570ee944bd2a5f5606507fee2f1b0f9d463843eeac90092cac",
    "run_synthetic": "0b25a697ea39cca8dff9ac26951807786a98428fa135c73dc8359809276f92c2",
    "log_synthetic": "8feddb7f4a68bfdf306985a01844ece0eb0891d88703fbd7b65287e2ea2c2ed5",
    "run_manual": "19b5403066bfce99fd5b5a765b71e645db5e5f3e86de182393f52bf0b4cf6242",
    "log_manual": "03b525f4c93f3ecfbff1837126d718a3591afe45f5d2ae075792ccd8f6ece364",
}
READS = {
    "physical": ("/workspace/denovo-example-io-1/samples/63924A-V3-2-V3LOOP_S74/"
                 "63924A-V3-2-V3LOOP_S74_L001_R1_001.fastq.gz",
                 "/workspace/denovo-example-io-1/samples/63924A-V3-2-V3LOOP_S74/"
                 "63924A-V3-2-V3LOOP_S74_L001_R2_001.fastq.gz",
                 "f971b40df8e14d1ba4d499d60065badc64fb7ba6afb11d45ddf6c3e8b385039e"),
    "synthetic": ("/workspace/ivanka-synthetic-abundance15-464-20261117/ultradeep-s003/reads/R1.fastq.gz",
                  "/workspace/ivanka-synthetic-abundance15-464-20261117/ultradeep-s003/reads/R2.fastq.gz",
                  "9411cc4e9464b629cd6e23461615d4e98972dacb5932f17a6f2017b5cf477013"),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def combined(a, b):
    h = hashlib.sha256()
    for idx, name in enumerate((a, b)):
        data = Path(name).read_bytes()
        h.update(bytes([idx]) + len(data).to_bytes(8, "big") + data)
    return h.hexdigest()


class Proposal(unittest.TestCase):
    def test_01_originals_untouched(self):
        self.assertEqual(sha(ACTIVE_REG), EXPECTED["active_registry"])
        self.assertEqual(sha(PRESERVED_REG), EXPECTED["preserved_registry"])
        for name in ("run_physical", "log_physical", "run_synthetic",
                     "log_synthetic", "run_manual", "log_manual"):
            base = "run-penguin-" if name.startswith("run_") else "run-penguin-"
            ident = {"physical": "1795549407618791948",
                     "synthetic": "1795554882243416925",
                     "manual": "1795630932807201880"}[name.split("_")[1]]
            with self.subTest(original=name):
                self.assertEqual(sha(ROOT / (base + ident + ".json" if name.startswith("run_")
                                             else base + ident + ".log")), EXPECTED[name])
        self.assertEqual(sha(ROOT / "receipts/image-penguin-frozen-8458f9e5-8e7c55a3.json"),
                         EXPECTED["image_receipt"])
        self.assertEqual(sha(IMAGE), EXPECTED["image_receipt"])
        active = json.loads(ACTIVE_REG.read_text())
        row = next(x for x in active["candidates"] if x["id"] == "penguin")
        self.assertEqual(row["status"], "source-pinned")
        self.assertIsNone(row["image_sha256"])
        self.assertFalse((ROOT / "handoff/penguin.json").exists())

    def test_02_input_hashes_and_combined_digests(self):
        data = json.loads(PILOT.read_text())
        for cohort, (r1, r2, expected) in READS.items():
            with self.subTest(cohort=cohort):
                self.assertEqual(sha(r1), data[cohort]["read_sha256"]["R1"])
                self.assertEqual(sha(r2), data[cohort]["read_sha256"]["R2"])
                self.assertEqual(combined(r1, r2), expected)
                self.assertEqual(data[cohort]["source_input_sha256"], expected)
        self.assertEqual(sha(ROOT / "pilots/penguin/physical-63924A-V3-2-V3LOOP_S74/conseq.csv"),
                         data["physical"]["conseq_sha256"])

    def test_03_receipt_fields_honest(self):
        data = json.loads(PILOT.read_text())
        self.assertEqual(data["schema"], "ivanka.exploratory.pilot.receipt.v1")
        self.assertEqual(data["physical"]["status"], "success")
        self.assertEqual(data["synthetic"]["status"], "failure")
        for cohort in ("physical", "synthetic"):
            self.assertTrue(data[cohort]["source_input_sha256"])
            self.assertEqual(data[cohort]["run_receipt_sha256"],
                             EXPECTED["run_" + cohort])
            self.assertEqual(data[cohort]["run_log_sha256"],
                             EXPECTED["log_" + cohort])
            self.assertTrue(data[cohort]["pilot_container_removed"])
        self.assertEqual(data["synthetic"]["run_receipt_sha256"], EXPECTED["run_synthetic"])
        self.assertEqual(data["synthetic"]["manual_followup_receipt_sha256"], EXPECTED["run_manual"])
        self.assertIsNone(data["synthetic"]["conseq_sha256"])
        self.assertIsNone(data["synthetic"]["observed_launcher_process_group_peak_rss_bytes"])
        self.assertEqual(data["synthetic"]["sampled_process_tree_rss_bytes_guard"], 3701882880)
        self.assertFalse(data["synthetic"]["guard_result"]["kernel_enforcement"])
        self.assertNotIn("scoring_attestation", data)
        self.assertNotIn("per_sample_results_sha256", data)
        self.assertFalse(data["qualifying"])
        self.assertFalse(data["seven_way_psi_release_inclusion"])

    def test_04_lease_teardown_proof(self):
        lines = [json.loads(l) for l in (ROOT / ".worker-lease.jsonl").read_text().splitlines()]
        by_lease = {}
        for line in lines:
            by_lease.setdefault(line.get("lease"), []).append(line)
        rec = by_lease["penguin-1795554882243416925"]
        self.assertTrue(any(r.get("state") == "reconciled" and
                            r.get("proof_receipt_sha256") == EXPECTED["run_synthetic"]
                            for r in rec))
        man = by_lease["penguin-1795630932807201880"]
        self.assertTrue(any(r.get("state") == "released" and
                            r.get("proof", {}).get("container_removed") is True and
                            r.get("cid") == "44d018921fc80cf7c4ad3a68f9b4f26694f769f71ff2a64ffdf30a45c559d12f"
                            for r in man))

    def test_05_proposed_registry_passes_current_policy(self):
        # Build a tiny TEMPORARY provenance root (JSON copies only) so the real
        # policy verifier can see all ten tools' receipts plus the two proposed
        # PenguiN receipts. Original receipts are never modified.
        import shutil
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="px-penguin-verify-", dir="/tmp/opencode"))
        try:
            for src in (ROOT / "receipts").glob("*.json"):
                shutil.copy2(src, tmp / src.name)
            for src in PROPOSED_RECEIPTS.glob("*.json"):
                shutil.copy2(src, tmp / src.name)
            reg = json.loads(PROPOSED_REG.read_text())
            for item in reg["candidates"]:
                for key in ("image_evidence", "pilot_evidence"):
                    ev = item.get(key)
                    if isinstance(ev, dict) and ev.get("path"):
                        ev["path"] = str(tmp / Path(ev["path"]).name)
            tmp_reg = tmp / "registry.json"
            tmp_reg.write_text(json.dumps(reg, sort_keys=True))
            data = pol.checked(tmp_reg, provenance_root=tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        row = next(x for x in data["candidates"] if x["id"] == "penguin")
        prop = json.loads(PROPOSED_REG.read_text())
        prow = next(x for x in prop["candidates"] if x["id"] == "penguin")
        bound = dict(prow, adapter_commit=data["adapter_branch_commits"]["penguin"])
        self.assertEqual(row["status"], "pilot")
        self.assertTrue(pol.verified_receipt(bound, prow["image_evidence"], "image",
                                             PROPOSED_RECEIPTS))
        self.assertTrue(pol.verified_receipt(bound, prow["pilot_evidence"], "pilot",
                                             PROPOSED_RECEIPTS))
        self.assertTrue(pol.eligible(data, "penguin"))
        self.assertTrue(pol.cohort_eligible(data, "penguin"))
        self.assertFalse(data["qualifying"])
        self.assertEqual(data["policy"]["min_workspace_free_bytes"], 32 * 1024**3)
        self.assertEqual(data["policy"]["max_concurrent_exploratory_workers"], 1)
        self.assertEqual(data["policy"]["max_container_wall_seconds"], 2400)
        self.assertEqual(data["policy"]["max_sampled_process_tree_rss_bytes"], 4_000_000_000)

    def test_06_mount_argv_contract_and_residual_gap_recorded(self):
        execution = (REPO / "benchmarks/assembler_bench/px_execution.py").read_text()
        pilot = (REPO / "benchmarks/assembler_bench/exploratory_runtime/pilot.py").read_text()
        self.assertIn('{_reads_mount(case)}:/reads:ro', execution)
        self.assertIn("assert_reference_blind(argv)", execution)
        self.assertIn('"--network=none"', pilot)
        self.assertIn('RAM_LIMIT = 4_000_000_000', pilot)
        doc = (HERE / "PENGUIN_ADMISSION_PROPOSAL_20261126.md").read_text()
        for token in ("raw argv", "argv_sha256", "not retained", "legacy helper",
                      "both-success", "no proxy", "widen", "no scoring"):
            self.assertIn(token, doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
