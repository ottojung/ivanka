"""Project reference selection must be IVA-controlled and nucleotide-only."""
import csv
import tempfile
import unittest
from pathlib import Path

from project_references import choose_reference, aligned_to_project_reference


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.iva = self.base / "iva"
        self.ivanka = self.base / "ivanka"
        self.iva.mkdir()
        self.ivanka.mkdir()
        self.catalog = {"projects": {"HLA-B": {"regions": [
            {"seed_region_names": ["HLA-B-seed"]}]}},
            "regions": {"HLA-B-seed": {"is_nucleotide": True,
                                       "reference": ["AAACCCGGGTTT"]}}}

    def test_iva_selected_reference_is_shared(self):
        (self.iva / "remap_counts.csv").write_text(
            "sample,type,count\nx,remap-final 1-HLA-B-seed-excluded,23\n")
        for directory, sequence in ((self.iva, "AAACCCGGGTTT"),
                                    (self.ivanka, "AAACCCGGG")):
            with (directory / "conseq.csv").open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(("consensus-percent-cutoff", "sequence"))
                writer.writerow(("MAX", sequence))
        result = aligned_to_project_reference(self.iva, self.ivanka,
                                              self.catalog, "HLA-B")
        self.assertEqual(result["name"], "HLA-B-seed")
        self.assertEqual(result["iva_best_local_score"], 12)
        self.assertEqual(result["ivanka_best_local_score"], 9)
        self.assertEqual(len(result["reference_sha256"]), 64)

    def test_seed_excluded_suffix_selects_seed_name(self):
        self.catalog["regions"]["HLA-B"] = {"is_nucleotide": True, "reference": ["CCCC"]}
        self.catalog["projects"]["HLA-B"]["regions"][0]["seed_region_names"].append("HLA-B")
        (self.iva / "remap_counts.csv").write_text(
            "sample,type,count\nx,remap-final 1-HLA-B-seed-excluded,23\n")
        name, sequence = choose_reference(self.iva, self.catalog, "HLA-B")
        self.assertEqual((name, sequence), ("HLA-B-seed", "AAACCCGGGTTT"))

    def test_no_hxb2_fallback_for_unknown_project(self):
        with self.assertRaises(KeyError):
            choose_reference(self.iva, self.catalog, "MidHCV")
