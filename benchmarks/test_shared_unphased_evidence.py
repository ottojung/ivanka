"""Proof guards for redacted, original-pair shared-local observations."""
import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared_unphased_evidence import build_shared_evidence
from test_shared_block_phase_links import fixture, pair


class SharedUnphasedEvidenceTests(unittest.TestCase):
    def test_redacted_by_default_no_phase_or_independent_molecules(self):
        masked, refs = fixture()
        rows = pair("one", "private-id-a", refs["one"])
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        encoded = json.dumps(result)
        self.assertFalse(result["raw_qnames_included"])
        self.assertNotIn("private-id-a", encoded)
        self.assertFalse(result["full_length_haplotype_phase_inferred"])
        self.assertFalse(result["independent_molecules_inferred"])
        self.assertFalse(result["insert_bases_imputed"])
        self.assertTrue(all(not n["is_phased"] for n in result["nodes"]))
        self.assertGreater(result["strict_original_read_pair_ids_evaluated"], 0)

    def test_opt_in_original_qname_provenance(self):
        masked, refs = fixture()
        rows = pair("one", "private-id-a", refs["one"])
        result = build_shared_evidence(
            masked, refs, rows, anchor=8, radius=100,
            include_qnames=True)
        self.assertTrue(result["raw_qnames_included"])
        self.assertIn("private-id-a", result["original_qname_provenance"])
        self.assertTrue(all("original_qnames" in n for n in result["nodes"]))

    def test_duplicate_complete_pairs_count_signature_once(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("one", "b", refs["one"])
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        block = [n for n in result["nodes"] if n["feature_kind"] == "block"]
        self.assertEqual(len(block), 1)
        self.assertEqual(block[0]["original_read_pair_ids"], 2)
        self.assertEqual(block[0]["distinct_consistent_pair_sequence_signatures"], 1)

    def test_partial_duplicate_signature_withheld_from_distinct_support(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("one", "b", refs["one"])
        rows[2]["qual"] = "!"*len(rows[2]["qual"])
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        block = [n for n in result["nodes"] if n["feature_kind"] == "block"]
        self.assertEqual(len(block), 1)
        self.assertEqual(block[0]["original_read_pair_ids"], 1)
        self.assertEqual(block[0]["distinct_consistent_pair_sequence_signatures"], 0)

    def test_contradictory_alleles_cannot_count_as_two_distinct_pairs(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("two", "b", refs["two"])
        # Force a same-signature collision across conflicting original
        # marker observations, to exercise the conservative aggregation.
        with patch("shared_unphased_evidence._pair_signature",
                   return_value=("same-sequence", "same-sequence")):
            result = build_shared_evidence(masked, refs, rows, 8, 100)
        markers = [n for n in result["nodes"]
                   if n["feature_kind"] == "marker"]
        self.assertEqual({n["observed_allele"] for n in markers}, {"A", "G"})
        self.assertTrue(all(
            n["distinct_consistent_pair_sequence_signatures"] == 0
            for n in markers))

    def test_unobserved_insert_cannot_create_marker_evidence(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"], start=80, mate_start=250)
        rows[0]["seq"] = refs["one"][80:145]
        rows[0]["qual"] = "I"*65
        rows[0]["cigar"] = "65M"
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        self.assertFalse(result["insert_bases_imputed"])
        self.assertFalse(any(n["feature_kind"] == "marker"
                             for n in result["nodes"]))

    def test_bad_search_parameter_fails_closed(self):
        masked, refs = fixture()
        with self.assertRaises(ValueError):
            build_shared_evidence(masked, refs, [], anchor=0)
        with self.assertRaises(ValueError):
            build_shared_evidence(masked, refs, [], minimum_quality=-1)
        with self.assertRaises(ValueError):
            build_shared_evidence(masked, refs, [], include_qnames="yes")

    def test_repeated_qname_is_not_a_strict_original_pair(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) * 2
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        self.assertEqual(result["strict_original_read_pair_ids_evaluated"], 0)
        self.assertEqual(result["nodes"], [])




class SharedUnphasedEvidenceSidecarTests(unittest.TestCase):
    def test_sidecar_schema_and_phase_never_inferred(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"])
        from shared_unphased_evidence import build_shared_evidence
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        self.assertEqual(result["schema_version"], "ivanka.shared_unphased_evidence.v1")
        self.assertEqual(result["selected_reference_names"], list(refs))
        self.assertEqual(result["artifact_type"], "shared_unphased_evidence_sidecar")
        self.assertFalse(result["full_length_haplotype_phase_inferred"])
        self.assertFalse(result["phase_inferred"])
        self.assertEqual(result["phase_status"], "unidentified")
        self.assertFalse(result["independent_molecules_inferred"])
        self.assertFalse(result["insert_bases_imputed"])
        self.assertTrue(result["original_read_pair_qnames_counted_once"])
        self.assertNotIn("molecules_not_doubled", result)

    def test_pair_counted_once_not_multiplied(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("one", "b", refs["one"])
        from shared_unphased_evidence import build_shared_evidence
        result = build_shared_evidence(masked, refs, rows, 8, 100)
        block = [n for n in result["nodes"] if n["feature_kind"] == "block"][0]
        self.assertEqual(block["original_read_pair_ids"], 2)
        self.assertEqual(block["distinct_consistent_pair_sequence_signatures"], 1)

class SidecarCliTests(unittest.TestCase):
    def test_original_csv_cli_creates_hash_attested_redacted_json(self):
        masked, refs = fixture()
        rows = pair("one", "private-synthetic-read", refs["one"])
        from shared_unphased_evidence import main
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            final, seeds, sam, output = (root / n for n in
                ("conseq.csv", "remap_conseq.csv", "remap.csv", "sidecar.json"))
            for path, fields, values in (
                (final, ("region","q-cutoff","consensus-percent-cutoff","sequence"),
                 [{"region":"one","q-cutoff":"15",
                   "consensus-percent-cutoff":"MAX","sequence":masked.sequence}]),
                (seeds, ("region","sequence"),
                 [{"region":name,"sequence":seq} for name,seq in refs.items()]),
                (sam, tuple(rows[0]), rows)):
                with path.open("w",newline="") as f:
                    writer=csv.DictWriter(f,fieldnames=fields)
                    writer.writeheader();writer.writerows(values)
            args=["sidecar",str(final),str(seeds),str(sam),"--region","one"]
            for name in refs:
                args.extend(["--reference",name])
            args += ["--mask-start","100","--mask-end","103",
                     "--anchor","8","--radius","100","--output",str(output)]
            with patch.object(sys,"argv",args):
                main()
            report=json.loads(output.read_text())
            self.assertEqual(report["selected_reference_names"],list(refs))
            self.assertEqual(report["mask_end"]-report["mask_start"],3)
            self.assertEqual(report["phase_status"],"unidentified")
            self.assertFalse(report["raw_qnames_included"])
            self.assertNotIn("private-synthetic-read",output.read_text())
            for name,path in (("final_conseq_csv",final),
                              ("remap_conseq_csv",seeds),
                              ("remap_sam_csv",sam)):
                self.assertEqual(report["input_provenance"][name]["sha256"],
                                 hashlib.sha256(path.read_bytes()).hexdigest())

if __name__ == "__main__":
    unittest.main()
