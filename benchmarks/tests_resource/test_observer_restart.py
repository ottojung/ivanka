"""Source-proven observer restart cannot silently lose measured RAM."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from benchmarks.resource_telemetry.containers import decode
from benchmarks.resource_telemetry.reconcile import reconcile
from benchmarks.resource_telemetry.records import create, persist, update


class ObserverRestartTests(unittest.TestCase):
    def test_closes_missing_observation_only_and_preserves_peaks(self):
        with TemporaryDirectory() as tmp:
            names = ("ivanka-bench-ivanka-abyss-A",
                     "ivanka-bench-ivanka-velvet-B",
                     "ivanka-bench-ivanka-spades-C")
            old, live, done = [create(str(i)*12, name)
                               for i, name in enumerate(names, 1)]
            update(old, (1400, 1200, 2))
            update(live, (900, 800, 1))
            done["observation_ended"] = True
            for row in (old, live, done):
                persist(tmp, row)
            listing = {"2"*12: (names[1], 123)}
            self.assertEqual(reconcile(tmp, listing), 1)
            self.assertEqual(reconcile(tmp, listing), 0)
            a = json.loads((Path(tmp)/("1"*12+".json")).read_text())
            b = json.loads((Path(tmp)/("2"*12+".json")).read_text())
            self.assertEqual(a["observation_end_cause"],
                             "monitor_restart_unobserved")
            self.assertEqual(a["peak_tree_rss_bytes_sampled"], 1400)
            self.assertEqual(a["peak_tree_pss_bytes_sampled"], 1200)
            self.assertEqual(a["samples"], 1)
            self.assertFalse(b["observation_ended"])
            self.assertNotIn("observation_end_cause", b)

    def test_refuse_recycled_identity_and_missing_process_id(self):
        with TemporaryDirectory() as tmp:
            row = create("a"*12, "ivanka-bench-ivanka-abyss-old")
            persist(tmp, row)
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                reconcile(tmp, {"a"*12: ("ivanka-bench-ivanka-abyss-new", 2)})
            with self.assertRaisesRegex(ValueError, "unavailable"):
                decode("a"*12+" ivanka-bench-ivanka-abyss-old 0\n")


if __name__ == "__main__":
    unittest.main()
