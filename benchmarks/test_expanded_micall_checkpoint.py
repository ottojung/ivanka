"""Idempotent MiCall benchmark restart, output integrity and fail-closed reuse."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from expanded.adapters import ASSEMBLERS
from expanded import micall_synthetic as runner
from expanded.micall_checkpoint import (
    digest, existing_case, identity, write_case,
)
from expanded.micall_retention import prune_case, prune_completed


def make_case(home):
    case = home / "case"
    case.mkdir()
    manifest = {"family": "clonal", "sha256": {
        "reads/R1.fastq.gz": "a" * 64,
        "reads/R2.fastq.gz": "b" * 64,
    }}
    proof = {"schema": "ivanka.hxb2_truth_validation.v1", "valid": True}
    images = {tool: (hex(i + 1)[2:] * 64)[:64]
              for i, tool in enumerate(ASSEMBLERS)}
    return case, manifest, proof, images


def completed_row(folder, manifest, proof, images):
    fields = identity("clonal-s000", manifest, proof)
    row = {**fields, "execution_order": list(ASSEMBLERS), "results": {}}
    folder.mkdir()
    for name in ASSEMBLERS:
        arm = folder / name
        arm.mkdir()
        (arm / "conseq_all.csv").write_text("final sequence\n")
        (arm / "remap_counts.csv").write_text("final counts\n")
        record = {
            "status": "success", "score_origin": runner.SCORE_ORIGIN,
            "timing_origin": runner.TIMING_ORIGIN,
            "sha256": images[name], "exit_code": 0,
            "seconds": 2.0, "score": 0.8,
            "final_dominant": {
                "source_output": "conseq_all.csv",
                "conseq_csv_sha256": digest(arm / "conseq_all.csv"),
                "remap_counts_sha256": digest(arm / "remap_counts.csv"),
            },
        }
        (arm / "execution.json").write_text(json.dumps(record) + "\n")
        row["results"][name] = record
    write_case(folder, row)
    return row


class SyntheticCheckpointTests(unittest.TestCase):
    def test_prune_only_verified_completed_cases_preserving_final_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            _, manifest, proof, images = make_case(home)
            folder = home / "clonal-s000"
            row = completed_row(folder, manifest, proof, images)
            for arm in ASSEMBLERS:
                scratch = folder / arm / "scratch"
                scratch.mkdir()
                (scratch / "temporary.bam").write_bytes(b"intermediate")
            (home / "run_manifest.json").write_text(json.dumps({
                "images": images, "source_truth": proof}))
            (home / "results.jsonl").write_text(json.dumps(row) + "\n")
            self.assertEqual(prune_completed(home), (1, 7))
            self.assertEqual(prune_completed(home), (1, 0))
            self.assertEqual(existing_case(folder,
                             identity("clonal-s000", manifest, proof), images), row)
            for arm in ASSEMBLERS:
                self.assertFalse((folder / arm / "scratch").exists())
                self.assertTrue((folder / arm / "execution.json").exists())
                self.assertTrue((folder / arm / "conseq_all.csv").exists())

    def test_tampered_final_output_prevents_any_scratch_pruning(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            _, manifest, proof, images = make_case(home)
            folder = home / "clonal-s000"
            row = completed_row(folder, manifest, proof, images)
            for arm in ASSEMBLERS:
                (folder / arm / "scratch").mkdir()
            (folder / "ivanka" / "conseq_all.csv").write_text("altered")
            with self.assertRaisesRegex(ValueError, "modified cached"):
                prune_case(home, row, images, proof)
            for arm in ASSEMBLERS:
                self.assertTrue((folder / arm / "scratch").exists())

    def test_failed_arms_retain_scratch_for_diagnosis(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            _, manifest, proof, images = make_case(home)
            folder = home / "clonal-s000"
            row = completed_row(folder, manifest, proof, images)
            failed = row["results"]["abyss"]
            failed["status"] = "failed"
            failed["seconds"] = None
            failed.pop("final_dominant")
            write = folder / "abyss" / "execution.json"
            write.write_text(json.dumps(failed) + "\n")
            (folder / "matrix.json").write_text(json.dumps(row) + "\n")
            for arm in ASSEMBLERS:
                (folder / arm / "scratch").mkdir()
            self.assertEqual(prune_case(home, row, images, proof), 6)
            self.assertTrue((folder / "abyss" / "scratch").exists())

    def test_partial_stream_and_duplicate_ids_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            _, manifest, proof, images = make_case(home)
            folder = home / "clonal-s000"
            row = completed_row(folder, manifest, proof, images)
            (home / "run_manifest.json").write_text(json.dumps({
                "images": images, "source_truth": proof}))
            (home / "results.jsonl").write_text(json.dumps(row)+"\n"+"{partial")
            self.assertEqual(prune_completed(home), (1, 0))
            (home / "results.jsonl").write_text((json.dumps(row)+"\n")*2)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                prune_completed(home)

    def test_cached_case_requires_unchanged_final_micall_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            _, manifest, proof, images = make_case(home)
            folder = home / "clonal-s000"
            row = completed_row(folder, manifest, proof, images)
            fields = identity("clonal-s000", manifest, proof)
            self.assertEqual(existing_case(folder, fields, images), row)
            (folder / "ivanka/conseq_all.csv").write_text("tampered\n")
            with self.assertRaisesRegex(ValueError, "modified cached"):
                existing_case(folder, fields, images)

    def test_cannot_reuse_different_image_digest_or_truth(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            _, manifest, proof, images = make_case(home)
            folder = home / "clonal-s000"
            completed_row(folder, manifest, proof, images)
            altered = dict(images)
            altered["ivanka"] = "f" * 64
            with self.assertRaisesRegex(ValueError, "cached tool"):
                existing_case(folder, identity("clonal-s000", manifest, proof),
                              altered)
            invalid = dict(proof, valid=False)
            with self.assertRaisesRegex(ValueError, "identity"):
                existing_case(folder, identity("clonal-s000", manifest, invalid),
                              images)

    def test_completed_case_does_not_run_any_assembler_again(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            case, manifest, proof, images = make_case(home)
            folder = home / "clonal-s000"
            previous = completed_row(folder, manifest, proof, images)
            with patch.object(runner, "attempt", side_effect=AssertionError):
                result = runner.run_case(("clonal-s000", case, manifest),
                                         home, images, proof, 40, resume=True)
            self.assertEqual(result, previous)

    def test_partially_interrupted_case_preserved_and_reexecuted(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            case, manifest, proof, images = make_case(home)
            partial = home / "clonal-s000"
            partial.mkdir()
            (partial / "old-logs.txt").write_text("do not destroy evidence")
            def fail_record(_case, dest, name, image, timeout):
                dest.mkdir()
                record = {
                    "status": "failed", "score_origin": runner.SCORE_ORIGIN,
                    "timing_origin": runner.TIMING_ORIGIN,
                    "sha256": image, "seconds": None, "score": 0,
                    "error": "controlled test failure",
                }
                (dest / "execution.json").write_text(json.dumps(record))
                return record
            with patch.object(runner, "attempt", side_effect=fail_record) as mock:
                result = runner.run_case(("clonal-s000", case, manifest),
                                         home, images, proof, 40, resume=True)
            self.assertEqual(mock.call_count, 7)
            self.assertEqual(len(result["results"]), 7)
            self.assertEqual((home / "_interrupted/clonal-s000-001/old-logs.txt")
                             .read_text(), "do not destroy evidence")
            self.assertTrue((home / "clonal-s000/matrix.json").is_file())
            self.assertFalse((home / "clonal-s000/matrix.json.partial").exists())

    def test_cli_forwards_resume_flag_without_restarting(self):
        from expanded.micall_synthetic import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pins = root / "pins.json"
            pins.write_text(json.dumps({tool: "a" * 64 for tool in ASSEMBLERS}))
            with (patch("sys.argv", ["micall_synthetic", "--data", str(root),
                                     "--images", str(pins), "--out", str(root),
                                     "--resume"]),
                  patch.object(runner, "run", return_value=400) as called):
                main()
            self.assertTrue(called.call_args.kwargs["resume"])

    def test_resume_refuses_changes_to_pinned_run_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            output = home / "run"
            output.mkdir()
            case, manifest, proof, images = make_case(home)
            pinned = runner.run_manifest(proof, images, None)
            pinned["images"] = dict(images, ivanka="f" * 64)
            (output / "run_manifest.json").write_text(json.dumps(pinned))
            cohort = [("case-" + str(i), case, manifest) for i in range(400)]
            with (patch.object(runner, "verify_images"),
                  patch.object(runner, "verify_ivanka_image_binding"),
                  patch.object(runner, "attestation", return_value=proof),
                  patch.object(runner, "cohort_rows", return_value=cohort),
                  patch.object(runner, "run_case", side_effect=AssertionError)):
                with self.assertRaisesRegex(ValueError, "manifest"):
                    runner.run(home, output, images, resume=True)

    def test_source_hashes_and_snapshot_immutability(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            _, manifest, proof, images = make_case(folder)
            pinned = runner.run_manifest(proof, images, None)
            self.assertEqual(pinned["instrumentation_sha256"], digest(runner.TIMER))
            self.assertIn("micall_checkpoint.py", pinned["benchmark_sources_sha256"])
            destination = folder / "clonal-s000"
            completed_row(destination, manifest, proof, images)
            with self.assertRaisesRegex(FileExistsError, ""):
                write_case(destination, {"bad": "duplicate"})


if __name__ == "__main__":
    unittest.main()


class SyntheticRunLockTests(unittest.TestCase):
    def test_concurrent_writers_must_fail_instead_of_corrupting_results(self):
        from expanded.micall_lock import exclusive_lock
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "run"
            with exclusive_lock(output):
                with self.assertRaisesRegex(ValueError, "active process"):
                    with exclusive_lock(output):
                        self.fail("a second benchmark writer obtained lock")
            with exclusive_lock(output):
                pass


class SyntheticFullResumeTests(unittest.TestCase):
    def test_resume_recovers_completed_cases_with_no_duplicate_results(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            case, manifest, proof, images = make_case(home)
            cohort = [(f"case-{i:03d}", case, manifest) for i in range(400)]
            output = home / "run"
            calls = []

            def failed_attempt(_case, dest, name, image, timeout):
                calls.append((dest.parent.name, name))
                dest.mkdir()
                record = {
                    "status": "failed", "score_origin": runner.SCORE_ORIGIN,
                    "timing_origin": runner.TIMING_ORIGIN, "sha256": image,
                    "seconds": None, "score": 0.0,
                    "error": "controlled nonqualifying test",
                }
                (dest / "execution.json").write_text(json.dumps(record))
                return record

            with (patch.object(runner, "verify_images"),
                  patch.object(runner, "verify_ivanka_image_binding"),
                  patch.object(runner, "attestation", return_value=proof),
                  patch.object(runner, "cohort_rows", return_value=cohort),
                  patch.object(runner, "attempt", side_effect=failed_attempt)):
                self.assertEqual(runner.run(home, output, images,
                                            jobs=2, limit=2), 2)
                self.assertEqual(len(calls), 14)
                original = json.loads(
                    (output / "attempt_completion.json").read_text())
                self.assertEqual(original["failed_assembler_arms"], 14)
                self.assertEqual(original["status"], "ATTEMPTED_NOT_QUALIFIED")
                self.assertEqual(runner.run(home, output, images,
                                            jobs=2, limit=2, resume=True), 2)
            self.assertEqual(len(calls), 14)
            rows = [json.loads(x) for x in
                    (output / "results.jsonl").read_text().splitlines()]
            self.assertEqual({r["id"] for r in rows},
                             {"case-000", "case-001"})
            self.assertEqual(len(rows), 2)
            self.assertEqual(len((output / "resume_history.jsonl")
                                 .read_text().splitlines()), 1)
            self.assertEqual(json.loads(
                (output / "attempt_completion.json").read_text())["status"],
                "ATTEMPTED_NOT_QUALIFIED")
