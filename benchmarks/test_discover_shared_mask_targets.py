"""Negative controls: never misidentify a reference-incompatible mask."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from discover_shared_mask_targets import discover, main
from test_shared_block_phase_links import fixture


def target():
    masked, refs = fixture()
    return [{"sample": "S", "region": "one", "sequence": masked.sequence,
             "q-cutoff": "15", "consensus-percent-cutoff": "MAX"}], refs


class MaskDiscoveryTests(unittest.TestCase):
    def test_exact_four_reference_shared_locus_with_target(self):
        rows, refs = target()
        result = discover(rows, refs, anchor=8, minimum_length=3,
                          region_contains="one")
        self.assertEqual(len(result["target_candidates"]), 1)
        case = result["target_candidates"][0]
        self.assertEqual((case["mask_start"], case["mask_end"]), (100, 103))
        self.assertEqual(case["selected_reference_names"], sorted(refs))
        self.assertTrue(case["target_reference_included"])
        self.assertFalse(result["independent_molecules_inferred"])
        self.assertFalse(result["haplotype_specific_depth_assigned"])

    def test_disallow_matching_other_references_without_target(self):
        rows, refs = target()
        del refs["one"]
        result = discover(rows, refs, 8, 3, "one")
        self.assertFalse(result["target_candidates"])
        self.assertEqual(result["reason_counts"],
                         {"target_reference_not_in_shared_group": 1})

    def test_competing_shared_locus_alleles_rejected(self):
        rows, refs = target()
        ref = refs["two"]
        refs["two"] = ref[:101] + ("A" if ref[101] != "A" else "C") + ref[102:]
        result = discover(rows, refs, 8, 3, "one")
        self.assertFalse(result["target_candidates"])
        self.assertEqual(result["reason_counts"],
                         {"competing_shared_locus_alleles": 1})

    def test_repeated_target_locus_fails_unique_match(self):
        rows, refs = target()
        ref = refs["one"]
        refs["one"] = ref + ref[92:111]
        result = discover(rows, refs, 8, 3, "one")
        self.assertFalse(result["target_candidates"])
        self.assertEqual(result["reason_counts"],
                         {"target_reference_not_in_shared_group": 1})

    def test_insufficient_or_ambiguous_flanks_never_selected(self):
        rows, refs = target()
        rows[0]["sequence"] = "xxx" + rows[0]["sequence"][3:]
        result = discover(rows, refs, 8, 3, "one")
        self.assertEqual(result["rejected_masks"][0]["reason"],
                         "insufficient_resolved_flanks")
        rows[0]["sequence"] = "N" * 8 + "xxx" + rows[0]["sequence"][11:]
        result = discover(rows, refs, 8, 3, "one")
        self.assertEqual(result["rejected_masks"][0]["reason"],
                         "non_ACGT_flanks")

    def test_uppercase_x_is_not_the_micall_lowercase_mask_convention(self):
        rows, refs = target()
        rows[0]["sequence"] = rows[0]["sequence"].replace("xxx", "XXX")
        self.assertEqual(discover(rows, refs, 8, 3, "one")["target_candidates"], [])
        self.assertEqual(discover(rows, refs, 8, 3, "one")["rejected_masks"], [])

    def test_no_empty_selector_or_missing_region(self):
        rows, refs = target()
        for invalid in ("", None):
            with self.assertRaises(ValueError):
                discover(rows, refs, 8, 3, invalid)
        rows[0]["sequence"] = None
        with self.assertRaises(ValueError):
            discover(rows, refs, 8, 3, "one")

    def test_short_masks_ignored_and_parameter_fail_closed(self):
        rows, refs = target()
        self.assertEqual(discover(rows, refs, 8, 4, "one")["target_candidates"], [])
        for anchor,minimum in ((0, 1), (8, 0), (True, 1), (8, False)):
            with self.assertRaises(ValueError):
                discover(rows, refs, anchor, minimum, "one")


class DiscoveryCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.sample = root / "original" / "sample1" / "ivanka"
        self.sample.mkdir(parents=True)
        self.report = root / "separate-diagnostics" / "candidate.json"
        rows, refs = target()
        self.rows = rows
        self.refs = refs
        for name,fields,values in (
            ("conseq.csv", ("sample","region","q-cutoff",
                            "consensus-percent-cutoff","sequence"),rows),
            ("remap_conseq.csv", ("region","sequence"),
             [{"region": k, "sequence": v} for k,v in refs.items()])):
            with (self.sample / name).open("w",newline="") as stream:
                writer=csv.DictWriter(stream,fieldnames=fields)
                writer.writeheader()
                writer.writerows(values)

    def invoke(self, output):
        args = ["discover",str(self.sample),"--anchor","8",
                "--minimum-length","3","--region-contains","one",
                "--output",str(output)]
        with patch.object(sys,"argv",args):
            main()

    def test_private_output_and_original_source_hashes(self):
        self.invoke(self.report)
        result=json.loads(self.report.read_text())
        self.assertEqual(result["sample_count"],1)
        self.assertEqual(len(result["target_candidates"]),1)
        self.assertEqual(self.report.stat().st_mode & 0o777,0o600)
        self.assertNotIn(self.rows[0]["sequence"],self.report.read_text())
        self.assertEqual(len(result["source_sha256"]["final_conseq_csv"]),64)

    def test_no_writes_inside_original_sample_tree(self):
        forbidden = self.sample.parent / "injected" / "new-report.json"
        with self.assertRaises(SystemExit):
            self.invoke(forbidden)
        self.assertFalse(forbidden.exists())

    def test_never_rewrites_existing_different_result(self):
        self.report.parent.mkdir()
        self.report.write_text("this is not equivalent")
        with self.assertRaises(SystemExit):
            self.invoke(self.report)
        self.assertEqual(self.report.read_text(),"this is not equivalent")

    def test_duplicate_remap_region_must_fail_closed(self):
        ref=self.sample/"remap_conseq.csv"
        with ref.open("a") as stream:
            stream.write("one,ACGT\n")
        with self.assertRaises(SystemExit):
            self.invoke(self.report)


if __name__ == "__main__":
    unittest.main()
