"""Focused acceptance tests: all final MAX contigs and all pinned references."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from reference_panel import (best_panel_alignment, build_reference_panel,
                             normalize_dna, panel_acceptance, panel_sha256)


def write_conseq(folder, sequences):
    folder.mkdir()
    (folder / "conseq.csv").write_text(
        "region,consensus-percent-cutoff,sequence\n"
        + "".join(f"r{i},MAX,{seq}\n" for i, seq in enumerate(sequences))
        + "ignored,0.5,ACGT\n"
    )


class ReferencePanelTests(TestCase):
    def test_chooses_best_independently_for_iva_and_riva(self):
        a = "ACGT" * 80
        b = "TGCATGCA" * 40
        references = (("A", a), ("B", b))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_conseq(root / "iva", ["TT", a, "AA"])
            write_conseq(root / "riva", ["CC", b, "GG"])
            result = panel_acceptance(root / "iva", root / "riva", references)
        self.assertEqual(result["iva_score"], 320)
        self.assertEqual(result["riva_score"], 320)
        self.assertTrue(result["pass"])
        self.assertEqual(result["iva_best_reference"], "A")
        self.assertEqual(result["riva_best_reference"], "B")
        self.assertEqual(result["reference_count"], 2)

    def test_five_percent_threshold_not_weakened(self):
        ref = "ACGT" * 100
        good = list(ref)
        bad = list(ref)
        for i in range(3):
            good[20 + i * 30] = "T" if good[20 + i * 30] != "T" else "A"
        for i in range(20):
            bad[20 + i * 16] = "T" if bad[20 + i * 16] != "T" else "A"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_conseq(root / "iva", [ref])
            write_conseq(root / "riva", ["".join(good)])
            self.assertTrue(panel_acceptance(root / "iva",root / "riva",[("ref",ref)])["pass"])
            (root / "riva" / "conseq.csv").write_text(
                "region,consensus-percent-cutoff,sequence\nr,MAX,"+"".join(bad)+"\n")
            self.assertFalse(panel_acceptance(root / "iva",root / "riva",[("ref",ref)])["pass"])

    def test_local_alignment_ignores_flanks_and_checks_reverse_strand(self):
        ref = "ACGTGCAATGCGATCGTACGTATCGGACCTTATACG" * 8
        query = ref[35:230]
        from Bio.Seq import Seq
        reversed_query = str(Seq(query).reverse_complement())
        result = best_panel_alignment(["TT", reversed_query], [("ref", ref)])
        self.assertEqual(result["score"], float(len(query)))

    def test_optional_simd_backend_preserves_exact_scores(self):
        import reference_panel
        from unittest.mock import patch
        if reference_panel.parasail is None:
            self.skipTest("optional parasail accelerator not installed")
        seq = "ACGTGCAATGGCTAACGCTAGCGTATCAGTCGAT" * 12
        variant = list(seq[30:330])
        for i in range(3, len(variant), 37):
            variant[i] = "T" if variant[i] != "T" else "A"
        candidates = [seq[40:300], "".join(variant)]
        refs = [("first", seq), ("second", "TTGGACCA" * 80)]
        simd = reference_panel.best_panel_alignment(candidates, refs)
        with patch.object(reference_panel, "parasail", None):
            scalar = reference_panel.best_panel_alignment(candidates, refs)
        self.assertEqual(simd, scalar)

    def test_missing_max_contigs_fail_closed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_conseq(root / "iva", ["ACGT" * 30])
            write_conseq(root / "riva", [])
            with self.assertRaisesRegex(ValueError, "Missing contigs"):
                panel_acceptance(root / "iva", root / "riva", [("ref", "ACGT" * 30)])

    def test_panel_from_pinned_catalog_and_ambiguity(self):
        hiv = "HIV1-B-TEST-seed"
        hcv = {n: {"reference": ["ACGT"*100], "is_nucleotide": True}
               for n in ("HCV-1a","HCV-1b","HCV-2a","HCV-2b","HCV-3a",
                         "HCV-3k","HCV-4a","HCV-4d","HCV-5a","HCV-6a","HCV-7a")}
        regions = {**hcv, hiv: {"reference": ["ACGTRYMK" * 100], "is_nucleotide": True},
                   "HLA-B-seed": {"reference": ["ACGT"*100], "is_nucleotide": True}}
        projects = {"projects":{"NFLHIVDNA":{"regions":[{"seed_region_names":[hiv]}]}},
                    "regions": regions}
        panel = build_reference_panel(projects, "ACGT"*2500)
        self.assertIn(("HCV-3k", "ACGT"*100), panel)
        self.assertTrue(any("HIV1-B:" in name for name, _ in panel))
        self.assertTrue(all(set(seq) <= set("ACGTN") for _, seq in panel))
        self.assertEqual(normalize_dna("ACGTRYMK"), "ACGTNNNN")
        self.assertEqual(panel_sha256(panel), panel_sha256(tuple(panel)))
