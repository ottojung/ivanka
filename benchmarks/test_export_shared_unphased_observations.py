"""Guards for shared unphased observation export: no phase, no double-count, authenticated verification."""
import csv, json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_shared_unphased_observations import (
    SCHEMA, ObservationExportError, consume_observations, export_observations,
    verify_observation_export, _canonical_json, _safe_write)
from test_shared_block_phase_links import fixture, pair


def write_synthetic(tmp, masked, refs, rows):
    root = Path(tmp)
    final = root / "conseq.csv"; seeds = root / "remap_conseq.csv"; sam = root / "remap.csv"
    with final.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=("region", "q-cutoff", "consensus-percent-cutoff", "sequence"))
        w.writeheader(); w.writerow({"region": "one", "q-cutoff": "15", "consensus-percent-cutoff": "MAX", "sequence": masked.sequence})
    with seeds.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=("region", "sequence")); w.writeheader()
        for n, s in refs.items(): w.writerow({"region": n, "sequence": s})
    with sam.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=tuple(rows[0])); w.writeheader(); w.writerows(rows)
    return final, seeds, sam


class ExportGuardTests(unittest.TestCase):
    def base(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("two", "b", refs["two"])
        return masked, refs, rows

    def test_explicit_unphased_no_overwrite_no_haplotype_assignment(self):
        masked, refs, rows = self.base()
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outd:
            f, s, sm = write_synthetic(td, masked, refs, rows)
            out = Path(outd) / "obs.json"
            r = export_observations(f, s, sm, region="one", references=list(refs),
                                    mask_start=100, mask_end=103, anchor=8)
            self.assertEqual(r["schema_version"], SCHEMA)
            self.assertTrue(r["unphased"])
            self.assertEqual(r["phase_status"], "unidentified")
            self.assertFalse(r["full_length_haplotype_phase_inferred"])
            self.assertFalse(r["original_fragment_assigned_to_competing_haplotypes"])
            self.assertFalse(r["haplotype_specific_depth_assigned"])
            self.assertFalse(r["independent_physical_molecules_assigned"])
            self.assertFalse(r["modifies_micall_consensus"])
            self.assertFalse(r["modifies_final_max_sequence"])
            self.assertFalse(r["safe_for_final_max_overwrite"])
            self.assertFalse(r["affects_198_acceptance"])
            self.assertFalse(r["raw_qnames_included"])
            self.assertNotIn("original_qnames", json.dumps(r))
            self.assertEqual(r["shared_reference_membership"]["selected_reference_names"], list(refs))
            status = verify_observation_export(r)
            self.assertTrue(status["verification"].startswith("passed_source_checksums"))
            self.assertFalse(status["modifies_micall_consensus"])
            _safe_write(r, out, [Path(td)])
            loaded = consume_observations(out, authenticated=True)
            self.assertEqual(loaded["consumer_mode"], "authenticated_recomputed")

    def test_per_site_spectrum_preserves_minority_alleles(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"]) + pair("two", "b", refs["two"])
        with tempfile.TemporaryDirectory() as td:
            f, s, sm = write_synthetic(td, masked, refs, rows)
            r = export_observations(f, s, sm, region="one", references=list(refs),
                                    mask_start=100, mask_end=103, anchor=8)
            sites = r["per_site_q15_observed_allele_spectrum"]
            self.assertEqual(len(sites), 3)
            for site in sites:
                self.assertIn("q15_original_pair_base_counts", site)
                self.assertTrue(site["pooled_across_selected_hypotheses"])
                self.assertFalse(site["assigned_to_single_haplotype"])

    def test_multi_hypothesis_same_qname_not_double_counted(self):
        masked, refs = fixture()
        rows = pair("one", "a", refs["one"])
        with tempfile.TemporaryDirectory() as td:
            f, s, sm = write_synthetic(td, masked, refs, rows)
            r = export_observations(f, s, sm, region="one", references=list(refs),
                                    mask_start=100, mask_end=103, anchor=8)
            self.assertEqual(r["strict_original_read_pair_ids_evaluated"], 1)
            for site in r["per_site_q15_observed_allele_spectrum"]:
                total = sum(site["q15_original_pair_base_counts"].values()) + site["q15_conflict_or_non_acgt_original_pair_ids"]
                self.assertLessEqual(total, 1)

    def test_tampered_site_counts_rejected(self):
        masked, refs, rows = self.base()
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outd:
            f, s, sm = write_synthetic(td, masked, refs, rows)
            r = export_observations(f, s, sm, region="one", references=list(refs),
                                    mask_start=100, mask_end=103, anchor=8)
            r["per_site_q15_observed_allele_spectrum"][0]["q15_original_pair_base_counts"]["A"] += 999
            out = Path(outd) / "tampered.json"; out.write_text(_canonical_json(r))
            with self.assertRaisesRegex(ObservationExportError, "deterministic recomputation"):
                consume_observations(out, authenticated=True)

    def test_tampered_source_checksum_rejected(self):
        masked, refs, rows = self.base()
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outd:
            f, s, sm = write_synthetic(td, masked, refs, rows)
            r = export_observations(f, s, sm, region="one", references=list(refs),
                                    mask_start=100, mask_end=103, anchor=8)
            r["source_checksums_sha256"]["remap_sam_csv"] = "0" * 64
            out = Path(outd) / "tampered.json"; out.write_text(_canonical_json(r))
            with self.assertRaisesRegex(ObservationExportError, "checksum mismatch"):
                consume_observations(out, authenticated=True)

    def test_untrusted_parse_explicitly_diagnostic_only(self):
        masked, refs, rows = self.base()
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outd:
            f, s, sm = write_synthetic(td, masked, refs, rows)
            r = export_observations(f, s, sm, region="one", references=list(refs),
                                    mask_start=100, mask_end=103, anchor=8)
            out = Path(outd) / "obs.json"; out.write_text(_canonical_json(r))
            parsed = consume_observations(out, authenticated=False)
            self.assertEqual(parsed["consumer_mode"], "untrusted_parse_diagnostic_only")
            self.assertFalse(parsed["empirical_use_permitted"])

    def test_consumer_rejects_unsafe_claims(self):
        bad = {"schema_version": SCHEMA, "unphased": True, "safe_for_final_max_overwrite": True,
               "modifies_micall_consensus": False, "full_length_haplotype_phase_inferred": False,
               "original_fragment_assigned_to_competing_haplotypes": False,
               "haplotype_specific_depth_assigned": False,
               "independent_physical_molecules_assigned": False,
               "raw_qnames_included": False, "minimum_phred_quality": 15}
        with tempfile.TemporaryDirectory() as outd:
            p = Path(outd) / "b.json"; p.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ObservationExportError, "Unsafe"):
                consume_observations(p, authenticated=False)

    def test_refuses_write_inside_source(self):
        masked, refs, rows = self.base()
        with tempfile.TemporaryDirectory() as td:
            f, s, sm = write_synthetic(td, masked, refs, rows)
            r = export_observations(f, s, sm, region="one", references=list(refs),
                                    mask_start=100, mask_end=103, anchor=8)
            with self.assertRaisesRegex(ObservationExportError, "Refusing to write"):
                _safe_write(r, f.parent / "obs.json", [f.parent])

    def test_below_q15_rejected(self):
        masked, refs, rows = self.base()
        with tempfile.TemporaryDirectory() as td:
            f, s, sm = write_synthetic(td, masked, refs, rows)
            with self.assertRaisesRegex(ObservationExportError, "Q15"):
                export_observations(f, s, sm, region="one", references=list(refs),
                                    mask_start=100, mask_end=103, anchor=8, minimum_quality=14)

    def test_require_fastq_rejected_without_attestation(self):
        masked, refs, rows = self.base()
        with tempfile.TemporaryDirectory() as td:
            f, s, sm = write_synthetic(td, masked, refs, rows)
            r = export_observations(f, s, sm, region="one", references=list(refs),
                                    mask_start=100, mask_end=103, anchor=8)
            self.assertFalse(r["original_fastq_mate_provenance"]["attested"])
            with self.assertRaisesRegex(ObservationExportError, "FASTQ provenance"):
                verify_observation_export(r, require_fastq=True)


if __name__ == "__main__":
    unittest.main()
