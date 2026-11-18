"""Resource monitor reports sampled peaks, without fabricating exact maxima."""
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from benchmarks.resource_telemetry import proc_tree
from benchmarks.resource_telemetry.proc_tree import sample_tree
from benchmarks.resource_telemetry.records import create, persist, update


class ResourceTelemetryTests(unittest.TestCase):
    def test_live_process_has_resident_and_proportional_memory(self):
        import os
        value = sample_tree(os.getpid())
        self.assertIsNotNone(value)
        self.assertGreater(value[0], 0)
        self.assertGreaterEqual(value[2], 1)

    def test_exited_zero_resident_descendant_has_exactly_zero_pss(self):
        with (patch.object(proc_tree, "Path") as fake,
              patch.object(proc_tree.os, "sysconf", return_value=4096)):
            fake.return_value.read_text.return_value = "0 0 0 0 0 0 0"
            fake.return_value.open.side_effect = FileNotFoundError()
            self.assertEqual(proc_tree.process_memory(1234), (0, 0))

    def test_missing_pss_for_resident_process_remains_unknown(self):
        with (patch.object(proc_tree, "Path") as fake,
              patch.object(proc_tree.os, "sysconf", return_value=4096)):
            fake.return_value.read_text.return_value = "5 2 0 0 0 0 0"
            fake.return_value.open.side_effect = PermissionError()
            self.assertEqual(proc_tree.process_memory(1234), (8192, None))

    def test_zero_resident_zombie_does_not_hide_live_pss_peak(self):
        with (patch.object(proc_tree, "descendants", return_value=[1, 2]),
              patch.object(proc_tree, "process_memory",
                           side_effect=[(10_000, 9_400), (0, 0)])):
            self.assertEqual(sample_tree(1), (10_000, 9_400, 2))

    def test_nonzero_missing_pss_remains_unreported(self):
        with (patch.object(proc_tree, "descendants", return_value=[1, 2]),
              patch.object(proc_tree, "process_memory",
                           side_effect=[(10_000, 9_400), (64, None)])):
            self.assertEqual(sample_tree(1), (10_064, None, 2))

    def test_monotone_peak_and_reload_do_not_lose_previous_observations(self):
        with TemporaryDirectory() as temp:
            name = "ivanka-bench-ivanka-abyss-000000000000-abc-00000000"
            record = create("a" * 64, name)
            update(record, (1000, 900, 2))
            update(record, (800, None, 1))
            persist(temp, record)
            again = create("a" * 64, name, temp)
            self.assertEqual(again["peak_tree_rss_bytes_sampled"], 1000)
            self.assertEqual(again["peak_tree_pss_bytes_sampled"], 900)
            self.assertEqual(again["pss_samples"], 1)
            self.assertEqual(again["samples"], 2)
            self.assertFalse(again["observation_ended"])
            self.assertNotIn("exact_peak_ram_bytes", again)

    def test_record_is_immutable_to_another_container_name(self):
        with TemporaryDirectory() as temp:
            record = create("a" * 64, "ivanka-bench-ivanka-abyss-one")
            persist(temp, record)
            with self.assertRaises(ValueError):
                create("a" * 64, "ivanka-bench-ivanka-abyss-other", temp)


if __name__ == "__main__":
    unittest.main()


class PodmanDiscoveryTests(unittest.TestCase):
    def test_single_listing_provides_host_pids(self):
        from benchmarks.resource_telemetry.containers import decode
        rows = ("abcabcabcabc ivanka-bench-ivanka-abyss-xyz 1201\n"
                "fedfedfedfed unrelated-service 2100\n"
                "123123123123 ivanka-bench-synth-xyz 3020\n")
        result = decode(rows)
        self.assertEqual(result, {
            "abcabcabcabc": ("ivanka-bench-ivanka-abyss-xyz", 1201),
            "123123123123": ("ivanka-bench-synth-xyz", 3020),
        })

    def test_rejects_ambiguous_listing_without_fabricating_measurements(self):
        from benchmarks.resource_telemetry.containers import decode
        for row in ("abcabcabcabc ivanka-bench-ivanka-abc garbage",
                    "abcabcabcabc ivanka-bench-ivanka-abc",
                    "zzzzzzzzzzzz ivanka-bench-ivanka-abc 1"):
            with self.subTest(row=row), self.assertRaises(ValueError):
                decode(row)
