"""Existing scratch archive retirement must be byte-exact and fail closed."""
import hashlib
import io
import json
import tarfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import migrate_scratch_archives as migration

CASE = "a" * 64


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _write_json(path, doc):
    path.write_text(json.dumps(doc, sort_keys=True) + "\n")


def _make_case(base, name=CASE, members=None, visual=True):
    root = Path(base)
    case = root / name
    case.mkdir(parents=True)
    (case / "conseq.csv").write_text("seed,consensus-percent-cutoff,sequence\na,MAX,ACGT\n")
    receipt = {
        "status": "success",
        "sample_sha256": name,
        "candidate_image_id": migration.CANDIDATE_IMAGE,
        "final_conseq_sha256": _digest((case / "conseq.csv").read_bytes()),
        "timing_origin": "micall_in_container_monotonic_v1",
        "sampled_rss_peak_bytes": 1000,
        "wall_seconds": 12.0,
        "violation": None,
    }
    _write_json(case / "prospective-execution.json", receipt)
    score = {
        "case_sha256": name,
        "candidate_execution_receipt_sha256": _digest(
            (case / "prospective-execution.json").read_bytes()),
        "candidate_conseq_sha256": receipt["final_conseq_sha256"],
        "reference_panel_sha256": migration.REFERENCE_PANEL,
        "score_floor_90pct_best_available": True,
        "score_floor_90pct_iva": True,
    }
    _write_json(case / "posthoc_score.json", score)
    if members is None:
        members = {
            "combined_contigs.fasta": b">c\nACGT\n",
            "assembly_tmp/contigs.fasta": b">a\nTTTT\n",
            "assembly_tmp/seeds.fasta": b">s\nGG\n",
            "assembly_tmp/assembler.log": b"assembled\n",
            "combined_contigs.csv": b"seed,len\na,4\n",
            "trimmed1.fastq": b"@r\nACGT\n+\nIIII\n",
            "temp.sam": b"sam data\n",
            "temp.fasta.1.bt2": b"index\n",
            "coverage.png": b"not a scientific record",
            "remap.csv": b"read-level table",
            "aligned.csv": b"read-level table",
        }
    archive = case / migration.ARCHIVE_NAME
    with tarfile.open(archive, "w:gz") as tar:
        for name_member, data in members.items():
            info = tarfile.TarInfo(name_member)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    files = [{"relative_path": name_member, "bytes": len(data),
              "sha256": _digest(data)} for name_member, data in sorted(members.items())]
    attestation = {
        "schema": migration.ATTESTATION_SCHEMA,
        "status": "complete",
        "qualification": False,
        "candidate_image_id": migration.CANDIDATE_IMAGE,
        "sha256_archive": _digest(archive.read_bytes()),
        "files": files,
        "source_execution_receipt_sha256": score["candidate_execution_receipt_sha256"],
        "source_posthoc_score_sha256": _digest((case / "posthoc_score.json").read_bytes()),
        "candidate_final_conseq_sha256": receipt["final_conseq_sha256"],
        "source_bytes_allocated": sum(len(data) for data in members.values()),
        "archive_bytes_allocated": archive.stat().st_size,
    }
    _write_json(case / migration.ATTESTATION_NAME, attestation)
    if visual:
        maps = case / "coverage_maps"
        maps.mkdir()
        (maps / "plot.png").write_bytes(b"plot")
        (case / "report.pdf").write_bytes(b"pdf")
    return case


def _args(root, temp, **overrides):
    values = {
        "root": Path(root),
        "cases": [],
        "limit": 0,
        "apply": False,
        "temp_dir": Path(temp),
        "lock": Path(temp) / "migration.lock",
        "max_temp_bytes": 64 * 1024 ** 2,
        "free_floor_bytes": 0,
        "reserve_bytes": 0,
        "image": migration.CANDIDATE_IMAGE,
        "panel": migration.REFERENCE_PANEL,
        "owner": "test",
    }
    values.update(overrides)
    return Namespace(**values)


class MigrateScratchArchivesTests(unittest.TestCase):
    def test_dry_run_only_plans(self):
        with TemporaryDirectory() as d:
            case = _make_case(d)
            before = {p.name: _digest(p.read_bytes()) for p in case.iterdir() if p.is_file()}
            plan = migration.inspect_case(case, _args(d, d))
            self.assertEqual(plan["retained_count"], 5)
            self.assertEqual(plan["discarded_count"], 6)
            self.assertEqual(before, {p.name: _digest(p.read_bytes())
                                      for p in case.iterdir() if p.is_file()})
            self.assertFalse((case / "retained-scratch").exists())

    def test_apply_promotes_then_removes_and_is_idempotent(self):
        with TemporaryDirectory() as d:
            case = _make_case(d)
            terminal = {name: _digest((case / name).read_bytes()) for name in
                        ("conseq.csv", "prospective-execution.json", "posthoc_score.json",
                         migration.ATTESTATION_NAME)}
            args = _args(d, d, apply=True)
            plan = migration.inspect_case(case, args)
            result = migration.apply_case(case, plan, args)
            self.assertEqual(result["status"], "migrated")
            self.assertFalse((case / migration.ARCHIVE_NAME).exists())
            self.assertFalse((case / "coverage_maps" / "plot.png").exists())
            self.assertFalse((case / "report.pdf").exists())
            for name, digest in terminal.items():
                self.assertEqual(_digest((case / name).read_bytes()), digest)
            retained = case / migration.RETAINED_SUBDIR
            self.assertEqual((retained / "combined_contigs.fasta").read_bytes(), b">c\nACGT\n")
            self.assertEqual((retained / "assembly_tmp" / "seeds.fasta").read_bytes(), b">s\nGG\n")
            self.assertFalse((retained / "trimmed1.fastq").exists())
            receipt = json.loads((case / migration.RECEIPT_NAME).read_text())
            self.assertTrue(receipt["archive_removed"])
            self.assertEqual(receipt["archive_sha256"], plan["archive_sha256"])
            self.assertEqual(len(receipt["retained_members"]), 5)
            self.assertEqual(len(receipt["discarded_members"]), 6)
            self.assertEqual(receipt["attestation_sha256"],
                             _digest((case / migration.ATTESTATION_NAME).read_bytes()))
            again = migration.apply_case(case, migration.inspect_case(case, args), args)
            self.assertEqual(again["status"], "already_migrated")

    def test_rejects_archive_hash_drift(self):
        with TemporaryDirectory() as d:
            case = _make_case(d)
            with (case / migration.ARCHIVE_NAME).open("ab") as stream:
                stream.write(b"\x00")
            with self.assertRaises(migration.MigrationError):
                migration.inspect_case(case, _args(d, d))
            self.assertTrue((case / migration.ARCHIVE_NAME).exists())

    def test_rejects_unattested_member(self):
        with TemporaryDirectory() as d:
            case = _make_case(d)
            archive = case / migration.ARCHIVE_NAME
            with tarfile.open(archive, "w:gz") as tar:
                payloads = {"combined_contigs.fasta": b">c\nACGT\n",
                            "unattested.csv": b"unexpected\n"}
                for name, data in payloads.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
            att = json.loads((case / migration.ATTESTATION_NAME).read_text())
            att["sha256_archive"] = _digest(archive.read_bytes())
            _write_json(case / migration.ATTESTATION_NAME, att)
            with self.assertRaises(migration.MigrationError):
                migration.inspect_case(case, _args(d, d))

    def test_rejects_conflicting_retained_file(self):
        with TemporaryDirectory() as d:
            case = _make_case(d)
            dest = case / migration.RETAINED_SUBDIR / "combined_contigs.fasta"
            dest.parent.mkdir()
            dest.write_bytes(b"conflicting\n")
            args = _args(d, d, apply=True)
            with self.assertRaises(migration.MigrationError):
                migration.apply_case(case, migration.inspect_case(case, args), args)
            self.assertTrue((case / migration.ARCHIVE_NAME).exists())
            self.assertEqual(dest.read_bytes(), b"conflicting\n")

    def test_bounded_temp_budget(self):
        with TemporaryDirectory() as d:
            case = _make_case(d)
            with self.assertRaises(migration.MigrationError):
                migration.inspect_case(case, _args(d, d, max_temp_bytes=8))
            self.assertTrue((case / migration.ARCHIVE_NAME).exists())

    def test_rejects_broken_terminal_receipt(self):
        with TemporaryDirectory() as d:
            case = _make_case(d)
            score = json.loads((case / "posthoc_score.json").read_text())
            score["score_floor_90pct_iva"] = False
            _write_json(case / "posthoc_score.json", score)
            with self.assertRaises(migration.MigrationError):
                migration.inspect_case(case, _args(d, d))

    def test_finalizes_after_crash_between_receipt_and_deletion(self):
        with TemporaryDirectory() as d:
            case = _make_case(d)
            args = _args(d, d, apply=True)
            plan = migration.inspect_case(case, args)
            promoted = migration._promote(case, plan)
            receipt = {
                "schema": migration.SCHEMA,
                "case_sha256": case.name,
                "attestation_sha256": plan["attestation_sha256"],
                "archive_sha256": plan["archive_sha256"],
                "archive_removed": False,
                "retained_members": promoted,
            }
            _write_json(case / migration.RECEIPT_NAME, receipt)
            (case / migration.ARCHIVE_NAME).unlink()
            result = migration.apply_case(case, migration.inspect_case(case, args), args)
            self.assertEqual(result["status"], "finalized")
            final = json.loads((case / migration.RECEIPT_NAME).read_text())
            self.assertTrue(final["archive_removed"])

    def test_rejects_visual_symlink(self):
        with TemporaryDirectory() as d:
            case = _make_case(d, visual=False)
            outside = Path(d) / "outside.png"
            outside.write_bytes(b"keep")
            (case / "linked.png").symlink_to(outside)
            args = _args(d, d, apply=True)
            migration.apply_case(case, migration.inspect_case(case, args), args)
            self.assertTrue((case / "linked.png").is_symlink())
            self.assertEqual(outside.read_bytes(), b"keep")

    def test_main_lock_and_limit(self):
        with TemporaryDirectory() as d:
            root = Path(d) / "cases"
            root.mkdir()
            for n in range(2):
                _make_case(root, name=f"{n:064x}")
            out = io.StringIO()
            with redirect_stdout(out):
                code = migration.main(["--root", str(root), "--temp-dir", d,
                                       "--limit", "1"])
            self.assertEqual(code, 0)
            report = json.loads(out.getvalue())
            self.assertEqual(len(report["cases"]), 1)
            self.assertEqual(report["cases"][0]["status"], "planned")


if __name__ == "__main__":
    unittest.main()
