import unittest
from .qualification import category, MAX_RSS


class QualificationTests(unittest.TestCase):
    def test_failed_never_becomes_qualified(self):
        self.assertEqual(category({"failed": True}, 10, {}), "failed")

    def test_old_long_success_is_disqualified(self):
        self.assertEqual(category({"arm": {"container_wall_seconds": 2401}},
                                  1, None), "over_40_minutes")

    def test_old_ram_heavy_success_is_disqualified(self):
        self.assertEqual(category({"arm": {"container_wall_seconds": 10}},
                                  MAX_RSS + 1, None), "observed_over_4GB")

    def test_no_ram_evidence_is_not_a_verified_pass(self):
        self.assertEqual(category({"arm": {"container_wall_seconds": 10}},
                                  None, None), "memory_unmeasured")

    def test_old_uncapped_run_is_not_a_verified_pass(self):
        self.assertEqual(category({"arm": {"container_wall_seconds": 10}},
                                  MAX_RSS - 1, None), "legacy_uncapped")

    def test_new_capped_run_only_observed_not_kernel_proven(self):
        a = {"memory_max_bytes": MAX_RSS, "podman_timeout_seconds": 2398}
        self.assertEqual(category({"arm": {"container_wall_seconds": 12}},
                                  MAX_RSS - 1, a),
                         "observed_within_budget_not_kernel_proven")
