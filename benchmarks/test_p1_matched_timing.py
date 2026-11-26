"""Tests for the diagnostic-only matched-resource timing plan."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import p1_matched_timing as plan_module  # noqa: E402

ORIGINAL_LOG = """\
2026-11-21 12:47:50,776[INFO]micall.main(): Starting on 670e5b5fa3a5 with 32 CPU's.
2026-11-21 12:47:52,235[INFO]micall.drivers.sample.process(): Running merge_for_entropy on Sample R1.fastq.gz.
2026-11-21 12:47:53,519[INFO]micall.drivers.sample.process(): Running fastq_g2p on Sample R1.fastq.gz.
2026-11-21 12:48:05,633[INFO]micall.drivers.sample.run_denovo(): Running de novo assembly on Sample R1.fastq.gz.
2026-11-21 12:48:07,605[INFO]micall.core.denovo.denovo(): Assembled 1 contigs in 0:00:01.972079 (1s) on /results/scratch/trimmed1.fastq.
2026-11-21 12:48:08,636[INFO]micall.drivers.sample.run_denovo(): Running remap on Sample R1.fastq.gz.
2026-11-21 12:48:19,478[INFO]micall.drivers.sample.process_post_assembly(): Running sam2aln on Sample R1.fastq.gz.
2026-11-21 12:48:36,455[INFO]micall.drivers.sample.process_post_assembly(): Running aln2counts on Sample R1.fastq.gz.
2026-11-21 12:49:14,878[INFO]micall.drivers.sample.process_post_assembly(): Running cascade_report on Sample R1.fastq.gz.
2026-11-21 12:50:09,759[INFO]micall.drivers.sample.process(): Finished sample Sample R1.fastq.gz.
Ivanka wrote 1 contigs in 1.9s
"""

CANDIDATE_LOG = """\
2026-11-24 18:28:41,767[INFO]micall.main(): Starting on 1bb5a8616fcc with 32 CPU's.
2026-11-24 18:28:49,106[INFO]micall.drivers.sample.process(): Running merge_for_entropy on Sample R1.fastq.gz.
2026-11-24 18:28:56,064[INFO]micall.drivers.sample.process(): Running fastq_g2p on Sample R1.fastq.gz.
2026-11-24 18:30:11,184[INFO]micall.drivers.sample.run_denovo(): Running de novo assembly on Sample R1.fastq.gz.
2026-11-24 18:30:23,000[INFO]micall.core.denovo.denovo(): Assembled 1 contigs in 0:00:11.814575 (11s) on /results/scratch/trimmed1.fastq.
2026-11-24 18:30:29,426[INFO]micall.drivers.sample.run_denovo(): Running remap on Sample R1.fastq.gz.
2026-11-24 18:31:30,139[INFO]micall.drivers.sample.process_post_assembly(): Running sam2aln on Sample R1.fastq.gz.
2026-11-24 18:33:18,713[INFO]micall.drivers.sample.process_post_assembly(): Running aln2counts on Sample R1.fastq.gz.
2026-11-24 18:35:39,796[INFO]micall.drivers.sample.process_post_assembly(): Running coverage_plots on Sample R1.fastq.gz.
2026-11-24 18:37:29,434[INFO]micall.drivers.sample.process_post_assembly(): Running cascade_report on Sample R1.fastq.gz.
2026-11-24 18:42:15,990[INFO]micall.drivers.sample.process(): Finished sample Sample R1.fastq.gz.
Ivanka wrote 1 contigs in 11.8s
"""


class MatchedTimingTests(unittest.TestCase):
    def test_argv_differs_only_by_image_and_result_dir(self) -> None:
        document = plan_module.plan()
        frozen = document["arms"]["frozen_ivanka"]
        candidate = document["arms"]["candidate_ivanka"]
        self.assertEqual(len(frozen), len(candidate))
        differences = [
            (a, b) for a, b in zip(frozen, candidate) if a != b
        ]
        # Image, result directory and the unique container name differ; every
        # resource flag, mount, timer and MiCall argument is byte-identical.
        self.assertEqual(len(differences), 3)
        changed = str(differences)
        self.assertIn("da795bbd", changed)
        self.assertIn("6fba7095", changed)
        self.assertIn("/OUT/FROZEN", changed)
        self.assertIn("/OUT/CANDIDATE", changed)
        self.assertIn("ivanka-p1-matched-ultradeep-s009-frozen_ivanka", changed)
        self.assertIn("ivanka-p1-matched-ultradeep-s009-candidate_ivanka", changed)

    def test_resources_are_matched_to_4gb_and_40m(self) -> None:
        document = plan_module.plan()
        invariants = document["invariants"]
        self.assertEqual(invariants["cpus"], "2")
        self.assertEqual(invariants["memory_bytes"], "4000000000")
        self.assertEqual(invariants["timeout_seconds"], "2400")
        for arm in document["arms"].values():
            self.assertIn("--cpus=2", arm)
            self.assertIn("--memory=4000000000", arm)
            self.assertEqual(arm[arm.index("--timeout") + 1], "2400")
            self.assertEqual(arm[arm.index("--stop-timeout") + 1], "2")
        self.assertTrue(invariants["same_read_mount"])
        self.assertEqual(invariants["qualification_impact"], "none_diagnostic_only")
        self.assertEqual(invariants["one_wall_deadline_seconds"], 2400)
        self.assertTrue(invariants["exact_cid_fail_closed_rss_guard"])
        self.assertTrue(invariants["exact_cid_teardown_in_finally"])
        self.assertEqual(
            invariants["real_global_worker_lock"],
            "/workspace/ivanka-exploratory-ten-20261121/.global-worker.lock",
        )
        self.assertEqual(invariants["drift_conclusion"], "strong_evidence_not_causal_proof")

    def test_dry_run_launches_nothing(self) -> None:
        with mock.patch.object(plan_module.subprocess, "Popen", side_effect=AssertionError("launched")):
            with mock.patch("sys.stdout.write") as output:
                self.assertEqual(plan_module.main([]), 0)
        self.assertIn("ivanka.p1.matched-timing.v2", output.call_args_list[0][0][0])

    def test_execute_requires_lock_token(self) -> None:
        with tempfile.TemporaryDirectory(prefix="p1-matched-timing-test-") as folder:
            with mock.patch.object(plan_module.subprocess, "Popen", side_effect=AssertionError("launched")):
                with self.assertRaises(plan_module.Refusal):
                    plan_module.main(["--execute", "--output-root", folder])

    def test_output_root_cannot_touch_sealed_evidence(self) -> None:
        for protected in plan_module.PROTECTED_ROOTS:
            with self.assertRaises(plan_module.Refusal):
                plan_module.check_output_root(str(protected / "new-folder"))

    def test_pinned_reads_and_timer_are_verified(self) -> None:
        pins = plan_module.check_inputs()
        self.assertEqual(pins["R1.fastq.gz"], plan_module.READ_SHA256["R1.fastq.gz"])
        self.assertEqual(pins["R2.fastq.gz"], plan_module.READ_SHA256["R2.fastq.gz"])
        self.assertEqual(pins["inside_container_timing.py"], plan_module.TIMER_SHA256)

    def test_stage_parser_on_retained_logs(self) -> None:
        original = plan_module.parse_stages(ORIGINAL_LOG)
        candidate = plan_module.parse_stages(CANDIDATE_LOG)
        self.assertAlmostEqual(original["micall_assembly_seconds"], 1.972079, places=4)
        self.assertAlmostEqual(candidate["micall_assembly_seconds"], 11.814575, places=4)
        self.assertAlmostEqual(original["remap_to_sam2aln_seconds"], 10.842, places=2)
        self.assertAlmostEqual(candidate["remap_to_sam2aln_seconds"], 60.713, places=2)
        self.assertAlmostEqual(original["native_assembly_seconds"], 1.9, places=3)
        self.assertAlmostEqual(candidate["native_assembly_seconds"], 11.8, places=3)
        # Every measured post-assembly stage is slower in the candidate run:
        # this is host/resource drift, not a native-algorithm 5x regression.
        self.assertGreater(
            candidate["remap_to_sam2aln_seconds"]
            / original["remap_to_sam2aln_seconds"],
            4.0,
        )
        self.assertLess(candidate["native_assembly_seconds"], 20.0)

    def test_plan_is_json_serializable_and_read_only(self) -> None:
        document = plan_module.plan()
        encoded = json.dumps(document, sort_keys=True)
        self.assertIn("same_host_and_back_to_back_window", encoded)
        self.assertIn("no_truth_or_reference_access", encoded)


if __name__ == "__main__":
    unittest.main()
