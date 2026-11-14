"""An unchanged input is necessary, not sufficient, for output reuse."""
import unittest

from expanded.v2_reuse_inventory import (
    attested_image_set, authenticated_clock, certified_arm, same_case,
)


class ReuseInventoryTests(unittest.TestCase):
    def test_only_byte_identical_non_low_depth_case_can_be_considered(self):
        source = {"sha256": {"reads/R1.fastq.gz": "a" * 64,
                             "reads/R2.fastq.gz": "b" * 64,
                             "hidden-truth/haplotypes.fasta": "c" * 64},
                  "family": "clonal", "seed": 0, "pairs": 10000,
                  "read_length": 150, "nominal_fractions": [1.0],
                  "hxb2_ancestry": {"schema": "valid"},
                  "sampled_haplotype_pairs": [10000]}
        self.assertTrue(same_case("clonal-s000", source, source.copy()))
        self.assertFalse(same_case("low_depth-s000", source, source.copy()))
        changed = {**source, "pairs": 5000}
        self.assertFalse(same_case("clonal-s000", source, changed))
        changed = {**source, "sha256": {
            **source["sha256"], "reads/R1.fastq.gz": "0" * 64}}
        self.assertFalse(same_case("clonal-s000", source, changed))

    def test_image_source_attestation_must_bind_every_exact_tool(self):
        from expanded.adapters import ASSEMBLERS
        images = {tool: "a" * 64 for tool in ASSEMBLERS}
        record = {"images": {tool: {"image_sha256": "a" * 64}
                             for tool in ASSEMBLERS}}
        self.assertTrue(attested_image_set(images, record))
        record["images"]["abyss"]["image_sha256"] = "b" * 64
        self.assertFalse(attested_image_set(images, record))
        del record["images"]["velvet"]
        self.assertFalse(attested_image_set(images, record))

    def test_requires_identical_authentic_monotonic_clock(self):
        arm = {"seconds": 12.5}
        clock = {"seconds": 12.5,
                 "timing_origin": "micall_in_container_monotonic_v1",
                 "exit_code": 0}
        self.assertTrue(authenticated_clock(arm, clock))
        self.assertFalse(authenticated_clock(arm, {**clock, "seconds": 12.6}))
        self.assertFalse(authenticated_clock(arm, {**clock, "exit_code": 1}))
        self.assertFalse(authenticated_clock(
            arm, {**clock, "timing_origin": "host_wall_v1"}))

    def test_failure_or_missing_final_consensus_never_becomes_reusable(self):
        case = {"status": "success", "sha256": "a" * 64,
                "exit_code": 0, "seconds": 41.0, "score": 120.0,
                "score_origin": "micall_final_max_reference_panel_v1",
                "timing_origin": "micall_in_container_monotonic_v1",
                "final_dominant": {"conseq_csv_sha256": "b" * 64}}
        self.assertTrue(certified_arm(case, "a" * 64))
        for key, bad in (("status", "failed"), ("exit_code", 1),
                         ("seconds", 0), ("seconds", float("nan")),
                         ("score", -1), ("score", float("nan")),
                         ("score_origin", "assembler_fasta_diagnostic_v1"),
                         ("final_dominant", {})):
            with self.subTest(key=key, bad=bad):
                self.assertFalse(certified_arm({**case, key: bad}, "a" * 64))
        self.assertFalse(certified_arm(case, "c" * 64))


if __name__ == "__main__":
    unittest.main()
