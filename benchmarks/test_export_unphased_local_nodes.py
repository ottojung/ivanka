"""Local shared node may be emitted only with direct Q15 local support."""
import json
import tempfile
import unittest
from pathlib import Path

from export_unphased_local_nodes import decide_local_node, private_write
from shared_block_consensus_candidate import candidate_from_calls


def evidence(shared="ACG", pair_count=101, signatures=None):
    calls = [(i, f"pair{j}", base)
             for i, base in enumerate(shared)
             for j in range(pair_count)]
    sigs = signatures or {
        f"pair{j}": (f"ACG{j}", "TGA") for j in range(pair_count)}
    result = candidate_from_calls(
        shared, calls, required_depth=100, pair_signatures=sigs)
    observed = {"unphased": True, "phase_status": "unidentified",
                "modifies_final_max_sequence": False,
                "per_site_q15_observed_allele_spectrum": [
                    {"site_zero_based_in_mask": site["site"],
                     "q15_original_pair_base_counts": dict(site["allele_qnames"])}
                    for site in result["positions"]]}
    return observed, result


class SharedUnphasedLocalNodeTests(unittest.TestCase):
    def test_complete_direct_local_evidence_emits_not_a_haplotype(self):
        original, audit = evidence()
        result = decide_local_node(original, audit)
        self.assertTrue(result["eligible"])
        self.assertEqual(result["read_derived_local_allele"], "ACG")
        self.assertEqual(result["min_site_q15_original_pair_ids"], 101)
        self.assertEqual(result["complete_shared_local_original_pair_ids"], 101)
        self.assertFalse(result["full_length_haplotype_phase_proven"])
        self.assertFalse(result["safe_to_fill_existing_max_mask"])

    def test_99_qnames_do_not_meet_the_100_depth_rule(self):
        observation, audit = evidence(pair_count=99)
        result = decide_local_node(observation, audit)
        self.assertFalse(result["eligible"])
        self.assertIn("Q15_original_pair_or_distinct_sequence_site_depth",
                      result["rejection_reasons"])

    def test_identical_pair_sequences_cannot_create_fake_depth(self):
        sigs = {f"pair{j}": ("SAME", "SEQUENCE") for j in range(101)}
        observation, audit = evidence(signatures=sigs)
        result = decide_local_node(observation, audit)
        self.assertFalse(result["eligible"])

    def test_per_site_100_without_any_complete_pair_cannot_emit_node(self):
        # All three sites independently pass Q15 depth and distinct
        # paired-sequence signatures, yet no one pair saw the full block.
        shared = "ACG"
        calls = [(site, f"site{site}_pair{j}", base)
                 for site, base in enumerate(shared) for j in range(101)]
        signatures = {q: (f"SEQUENCE_{q}", "MATE")
                      for _, q, _ in calls}
        audited = candidate_from_calls(
            shared, calls, required_depth=100,
            pair_signatures=signatures)
        self.assertTrue(audited["eligible"])
        self.assertEqual(audited["complete_block_observations"][
            "shared_allele_complete_read_pair_ids"], 0)
        obs = {"unphased": True, "phase_status": "unidentified",
               "modifies_final_max_sequence": False,
               "per_site_q15_observed_allele_spectrum": [
                   {"site_zero_based_in_mask": item["site"],
                    "q15_original_pair_base_counts": dict(item["allele_qnames"])}
                   for item in audited["positions"]]}
        result = decide_local_node(obs, audited)
        self.assertFalse(result["eligible"])
        self.assertIn("insufficient_direct_complete_local_pair_signatures",
                      result["rejection_reasons"])

    def test_insufficient_complete_local_pair_evidence_rejected(self):
        obs, audit = evidence()
        result = decide_local_node(
            obs, audit, min_complete_signatures=102)
        self.assertFalse(result["eligible"])
        self.assertIn("insufficient_direct_complete_local_pair_signatures",
                      result["rejection_reasons"])

    def test_competing_minor_allele_at_one_site_vetoes_node(self):
        obs, audit = evidence()
        # Add a legitimate alternative at the first site so that
        # 101/111=0.91, below the conservative 95% allele fraction.
        sigs = {f"pair{j}": (f"ACG{j}", "TGA") for j in range(101)}
        sigs.update({f"alternative{j}": (f"GGG{j}", "TGA")
                     for j in range(10)})
        calls = [(i, f"pair{j}", base)
                 for i, base in enumerate("ACG") for j in range(101)]
        calls.extend((0, f"alternative{j}", "T") for j in range(10))
        audited = candidate_from_calls(
            "ACG", calls, required_depth=100, pair_signatures=sigs)
        obs["per_site_q15_observed_allele_spectrum"] = [
            {"site_zero_based_in_mask": p["site"],
             "q15_original_pair_base_counts": dict(p["allele_qnames"])}
            for p in audited["positions"]]
        result = decide_local_node(obs, audited)
        self.assertFalse(result["eligible"])
        self.assertIn("competing_minority_allele_fraction",
                      result["rejection_reasons"])

    def test_source_spectrum_mismatch_fails_closed(self):
        obs, audit = evidence()
        obs["per_site_q15_observed_allele_spectrum"][1][
            "q15_original_pair_base_counts"]["C"] += 1
        with self.assertRaisesRegex(ValueError, "spectrum mismatch"):
            decide_local_node(obs, audit)

    def test_unphased_status_and_thresholds_cannot_be_forged(self):
        obs, audit = evidence()
        for changes in ({"unphased": False},
                        {"modifies_final_max_sequence": True},
                        {"phase_status": "phased"}):
            changed = dict(obs, **changes)
            with self.assertRaises(ValueError):
                decide_local_node(changed, audit)
        for options in ({"depth": True}, {"depth": 0},
                        {"min_fraction": 0}, {"min_fraction": 1.2},
                        {"min_complete_signatures": 0}):
            with self.assertRaises(ValueError):
                decide_local_node(obs, audit, **options)

    def test_private_writer_does_not_modify_original_sources(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "original"
            source.mkdir()
            private = Path(td) / "private"
            fasta = private / "out.fasta"
            report = private / "out.json"
            data = {"schema_version": "test", "modifies_micall_consensus": False}
            with self.assertRaisesRegex(ValueError, "source tree"):
                private_write(">test\\nACG\\n", data, source / "out.fasta",
                              report, [source])
            self.assertFalse((source / "out.fasta").exists())
            private_write(">test\\nACG\\n", data, fasta, report, [source])
            self.assertEqual(fasta.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(report.read_text()), data)
            with self.assertRaisesRegex(ValueError, "existing"):
                private_write("", data, fasta, report, [source])


if __name__ == "__main__":
    unittest.main()
