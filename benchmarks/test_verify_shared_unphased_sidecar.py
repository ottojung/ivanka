"""Fail-closed contract tests against original synthetic paired SAM CSVs."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared_unphased_evidence import main as make_sidecar
from test_shared_block_phase_links import fixture, pair
from verify_shared_unphased_sidecar import EvidenceContractError, main, verify


class VerifiedSharedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.artifacts = root / "original-micall"
        (self.artifacts / "scratch").mkdir(parents=True)
        self.sidecar = root / "derived" / "sidecar.json"
        masked, refs = fixture()
        rows = pair("one", "private-synthetic-id", refs["one"])
        source_dir = root / "original-fastqs"
        source_dir.mkdir()
        self.raw_r1, self.raw_r2 = source_dir / "original_R1.fastq", source_dir / "original_R2.fastq"
        for m, row, path in ((1, rows[0], self.raw_r1),
                             (2, rows[1], self.raw_r2)):
            path.write_text("@private-synthetic-id/" + str(m) + "\n"
                            + row["seq"] + "\n+\n" + row["qual"] + "\n")
        self.csv_file("conseq.csv",
            ("region", "q-cutoff", "consensus-percent-cutoff", "sequence"),
            [{"region": "one", "q-cutoff": "15",
              "consensus-percent-cutoff": "MAX", "sequence": masked.sequence}])
        self.csv_file("remap_conseq.csv", ("region", "sequence"),
            [{"region": name, "sequence": seq} for name, seq in refs.items()])
        self.csv_file("scratch/remap.csv", tuple(rows[0]), rows)
        args = ["producer", str(self.artifacts / "conseq.csv"),
                str(self.artifacts / "remap_conseq.csv"),
                str(self.artifacts / "scratch/remap.csv"),
                "--region", "one"]
        for name in refs:
            args.extend(["--reference", name])
        args.extend(["--mask-start", "100", "--mask-end", "103",
                     "--anchor", "8", "--radius", "100",
                     "--output", str(self.sidecar)])
        with patch.object(sys, "argv", args):
            make_sidecar()

    def csv_file(self, relative, fields, rows):
        path = self.artifacts / relative
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_exact_recomputation_and_sanitized_non_coverage_status(self):
        status = verify(self.sidecar, self.artifacts)
        self.assertEqual(status["verification"],
                         "passed_source_sha256_and_exact_recomputation")
        self.assertNotIn("original_fastq_provenance", status)
        self.assertEqual(status["haplotype_phase"], "unidentified")
        self.assertFalse(status["independent_physical_molecules_assigned"])
        self.assertFalse(status["haplotype_specific_depth_assigned"])
        self.assertFalse(status["modifies_micall_consensus"])
        self.assertNotIn("private-synthetic-id", json.dumps(status))
        self.assertNotIn("SHARED_BLOCK:", json.dumps(status))

    def test_rejects_tampered_node_counts_even_with_valid_file_hashes(self):
        data = json.loads(self.sidecar.read_text())
        data["nodes"][0]["original_read_pair_ids"] += 1
        self.sidecar.write_text(json.dumps(data))
        with self.assertRaises(EvidenceContractError):
            verify(self.sidecar, self.artifacts)

    def test_rejects_later_input_mutation(self):
        with (self.artifacts / "scratch/remap.csv").open("a") as stream:
            stream.write("unreviewed,mutation\n")
        with self.assertRaisesRegex(EvidenceContractError, "modified source"):
            verify(self.sidecar, self.artifacts)

    def test_rejects_wrong_original_run_directory(self):
        alternative = Path(self.temp.name) / "other-sample"
        alternative.mkdir()
        with self.assertRaises(EvidenceContractError):
            verify(self.sidecar, alternative)

    def test_rejects_haplotype_claim_or_qname_disclosure(self):
        original = json.loads(self.sidecar.read_text())
        for edit in ({"phase_status": "phased"},
                     {"independent_molecules_inferred": True},
                     {"raw_qnames_included": True},
                     {"original_qname_provenance": {"private": []}}):
            changed = original.copy()
            changed.update(edit)
            self.sidecar.write_text(json.dumps(changed))
            with self.assertRaises(EvidenceContractError):
                verify(self.sidecar, self.artifacts)

    def test_low_quality_sidecar_does_not_pass_consumer(self):
        report = json.loads(self.sidecar.read_text())
        report["minimum_quality"] = 0
        self.sidecar.write_text(json.dumps(report))
        with self.assertRaisesRegex(EvidenceContractError, "below Q15"):
            verify(self.sidecar, self.artifacts)

    def test_cli_blocks_relative_escape_into_original_artifacts(self):
        escape = self.artifacts / "scratch" / ".." / "status.json"
        with patch.object(sys, "argv", ["consumer", str(self.sidecar),
                                         "--artifact-dir", str(self.artifacts),
                                         "--status-output", str(escape)]):
            with self.assertRaises(SystemExit):
                main()
        self.assertFalse((self.artifacts / "status.json").exists())

    def test_cli_never_overwrites_original_sidecar_or_changed_status(self):
        original = self.sidecar.read_bytes()
        with patch.object(sys, "argv", ["consumer", str(self.sidecar),
                                         "--artifact-dir", str(self.artifacts),
                                         "--status-output", str(self.sidecar)]):
            with self.assertRaises(SystemExit):
                main()
        self.assertEqual(self.sidecar.read_bytes(), original)
        output = Path(self.temp.name) / "report-status.json"
        output.write_text("different report")
        with patch.object(sys, "argv", ["consumer", str(self.sidecar),
                                         "--artifact-dir", str(self.artifacts),
                                         "--status-output", str(output)]):
            with self.assertRaises(SystemExit):
                main()
        self.assertEqual(output.read_text(), "different report")

    def test_optional_full_original_fastq_chain(self):
        status = verify(self.sidecar, self.artifacts, self.raw_r1, self.raw_r2)
        self.assertEqual(status["original_fastq_provenance"],
                         "sequence_and_phred_authenticated_per_original_mate")
        self.assertEqual(status["raw_original_read_pairs_scanned"], 1)
        self.assertEqual(status["original_remap_pair_ids_authenticated"], 1)
        self.assertEqual(status["haplotype_phase"], "unidentified")
        self.assertFalse(status["independent_physical_molecules_assigned"])
        self.assertFalse(status["modifies_micall_consensus"])
        self.assertNotIn("private-synthetic-id", json.dumps(status))

    def test_cannot_create_status_inside_original_fastq_source_directory(self):
        output = self.raw_r1.parent / "new-status.json"
        args = ["consumer", str(self.sidecar),
                "--artifact-dir", str(self.artifacts),
                "--original-fastq-r1", str(self.raw_r1),
                "--original-fastq-r2", str(self.raw_r2),
                "--status-output", str(output)]
        with patch.object(sys, "argv", args):
            with self.assertRaises(SystemExit):
                main()
        self.assertFalse(output.exists())

    def test_raw_fastq_mates_must_both_be_given(self):
        with self.assertRaisesRegex(EvidenceContractError, "Both original"):
            verify(self.sidecar, self.artifacts, self.raw_r1, None)

    def test_raw_fastq_quality_change_rejected(self):
        self.raw_r2.write_text(self.raw_r2.read_text().replace("I", "!"))
        with self.assertRaisesRegex(EvidenceContractError, "FASTQ mate provenance"):
            verify(self.sidecar, self.artifacts, self.raw_r1, self.raw_r2)

    def test_cli_with_raw_fastq_writes_distinct_schema(self):
        output = Path(self.temp.name) / "raw-verified-status.json"
        args = ["consumer", str(self.sidecar),
                "--artifact-dir", str(self.artifacts),
                "--original-fastq-r1", str(self.raw_r1),
                "--original-fastq-r2", str(self.raw_r2),
                "--status-output", str(output)]
        with patch.object(sys, "argv", args):
            main()
        data = json.loads(output.read_text())
        self.assertEqual(data["schema_version"],
                         "ivanka.unphased_sidecar_verification_raw_fastq.v1")
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_cli_status_output_never_mutates_micall_artifacts(self):
        root = Path(self.temp.name)
        output = root / "verified-status.json"
        with patch.object(sys, "argv", ["consumer", str(self.sidecar),
                                         "--artifact-dir", str(self.artifacts),
                                         "--status-output", str(output)]):
            main()
        result = json.loads(output.read_text())
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertFalse(result["affects_198_acceptance"])
        self.assertFalse(result["modifies_micall_consensus"])
        forbidden = self.artifacts / "scratch" / "verified-status.json"
        with patch.object(sys, "argv", ["consumer", str(self.sidecar),
                                         "--artifact-dir", str(self.artifacts),
                                         "--status-output", str(forbidden)]):
            with self.assertRaises(SystemExit):
                main()
        self.assertFalse(forbidden.exists())


if __name__ == "__main__":
    unittest.main()
