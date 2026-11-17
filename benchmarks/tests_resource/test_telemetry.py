"""Resource monitor reports sampled peaks, without fabricating exact maxima."""
from tempfile import TemporaryDirectory
import unittest

from benchmarks.resource_telemetry.proc_tree import sample_tree
from benchmarks.resource_telemetry.records import create, persist, update


class ResourceTelemetryTests(unittest.TestCase):
    def test_live_process_has_resident_and_proportional_memory(self):
        import os
        value = sample_tree(os.getpid())
        self.assertIsNotNone(value)
        self.assertGreater(value[0], 0)
        self.assertGreaterEqual(value[2], 1)

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
