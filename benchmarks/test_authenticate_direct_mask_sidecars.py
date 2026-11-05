"""Tests for read-only preserved direct-v2 sidecar authentication."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from authenticate_direct_mask_sidecars import authenticate
from shared_unphased_evidence import main as make_sidecar
from test_shared_block_phase_links import fixture, pair
from verify_shared_unphased_sidecar import EvidenceContractError


class AuthenticateDirectMaskSidecarsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.artifacts = root / "original-micall"
        (self.artifacts / "scratch").mkdir(parents=True)
        self.sidecar = root / "derived" / "sidecar.json"
        masked, refs = fixture()
        rows = pair("one", "private-synthetic-id", refs["one"])
        source_dir = root / "samples" / "sample-a"
        source_dir.mkdir(parents=True)
        self.raw_r1 = source_dir / "sample-a_L001_R1_001.fastq"
        self.raw_r2 = source_dir / "sample-a_L001_R2_001.fastq"
        for m, row, path in ((1, rows[0], self.raw_r1),
                             (2, rows[1], self.raw_r2)):
            path.write_text("@private-synthetic-id/" + str(m) + "\n"
                            + row["seq"] + "\n+\n" + row["qual"] + "\n")
        self._csv("conseq.csv",
            ("region", "q-cutoff", "consensus-percent-cutoff", "sequence"),
            [{"region": "one", "q-cutoff": "15",
              "consensus-percent-cutoff": "MAX", "sequence": masked.sequence}])
        self._csv("remap_conseq.csv", ("region", "sequence"),
            [{"region": n, "sequence": s} for n, s in refs.items()])
        self._csv("scratch/remap.csv", tuple(rows[0]), rows)
        args = ["producer", str(self.artifacts / "conseq.csv"),
                str(self.artifacts / "remap_conseq.csv"),
                str(self.artifacts / "scratch/remap.csv"),
                "--region", "one", "--direct-links"]
        for name in refs:
            args.extend(["--reference", name])
        args.extend(["--mask-start", "100", "--mask-end", "103",
                     "--anchor", "8", "--radius", "100",
                     "--output", str(self.sidecar)])
        with patch.object(sys, "argv", args):
            make_sidecar()

    def _csv(self, relative, fields, rows):
        path = self.artifacts / relative
        with path.open("w", newline="") as stream:
            import csv
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_authenticates_remap_and_raw_fastq_without_phase_claims(self):
        result = authenticate([{"sidecar": self.sidecar, "sample": "sample-a"}],
                              fastq_roots=[Path(self.temp.name) / "samples"])
        self.assertEqual(result["schema_version"],
                         "ivanka.direct_mask_sidecar_authentication.v1")
        self.assertEqual(result["record_count"], 1)
        r = result["records"][0]
        self.assertTrue(r["raw_fastq_authenticated"])
        self.assertEqual(r["verification_schema"],
                         "ivanka.unphased_sidecar_verification_direct_raw_fastq.v2")
        self.assertEqual(r["per_marker_direct_original_pair_observations"], [1])
        self.assertEqual(r["haplotype_phase"], "unidentified")
        self.assertFalse(r["cross_marker_pair_counts_summable"])
        self.assertFalse(r["independent_physical_molecules_assigned"])
        self.assertFalse(r["haplotype_specific_depth_assigned"])
        self.assertFalse(r["affects_198_acceptance"])
        self.assertNotIn("private-synthetic-id", json.dumps(result))
        self.assertIn("not additive", result["interpretation"])

    def test_fails_closed_on_tampered_sidecar(self):
        data = json.loads(self.sidecar.read_text())
        data["marker_direct_links"][0]["direct_joint_observation_count"] = 99
        self.sidecar.write_text(json.dumps(data))
        with self.assertRaises(EvidenceContractError):
            authenticate([self.sidecar])

    def test_refuses_output_inside_original_source_directory(self):
        out = self.artifacts / "scratch" / "audit.json"
        with self.assertRaises(EvidenceContractError):
            authenticate([{"sidecar": self.sidecar, "sample": "sample-a"}],
                         fastq_roots=[Path(self.temp.name) / "samples"],
                         output=out)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
