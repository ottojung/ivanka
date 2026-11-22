"""Nonqualifying candidate boundary must fail closed."""
import copy
import unittest
from pathlib import Path

from assembler_bench.exploratory_policy import checked, eligible

PATH = Path(__file__).parent / "assembler_bench/exploratory_candidates.json"


class TestExplorerRegistry(unittest.TestCase):
    def setUp(self):
        self.current = checked(PATH)

    def mutate(self, tmp_path, change):
        import json
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            target = Path(temp) / "candidates.json"
            data = copy.deepcopy(self.current)
            change(data)
            target.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                checked(target)

    def test_all_ten_source_pinned_but_unbuilt_and_nonqualifying(self):
        self.assertEqual(len(self.current["candidates"]), 10)
        self.assertTrue(all(x["status"] == "source-pinned"
                            and len(x["source_commit"]) == 40
                            and x["image_sha256"] is None
                            for x in self.current["candidates"]))
        self.assertTrue(all(not eligible(self.current, x["id"])
                            for x in self.current["candidates"]))

    def test_blocked_originals_retained_with_auditable_replacements(self):
        active = {x["id"]: x for x in self.current["candidates"]}
        self.assertEqual(set(active) & {"vicuna", "pehaplo"}, set())
        self.assertEqual(active["soapdenovo2"]["source_license"], "GPL-3.0")
        self.assertEqual(active["fermi-lite"]["source_license"], "MIT")
        blocked = {x["id"]: x for x in self.current["blocked_original_candidates"]}
        self.assertEqual(set(blocked), {"vicuna", "pehaplo"})
        self.assertEqual(blocked["vicuna"]["replacement"], "soapdenovo2")
        self.assertEqual(blocked["pehaplo"]["replacement"], "fermi-lite")
        self.assertTrue(all(x["qualifying"] is False and x["not_qualifying"] is True for x in blocked.values()))
        self.mutate(PATH, lambda d: d.pop("blocked_original_candidates"))
        self.mutate(PATH, lambda d: d["blocked_original_candidates"][0].update(
            status="image-pinned"))
        self.mutate(PATH, lambda d: d["candidates"][6].update(
            source_license="unknown"))
        self.mutate(PATH, lambda d: d["candidates"][7].update(
            image_sha256="0" * 64, status="pilot"))

    def test_must_not_add_to_original_qualifiers(self):
        self.mutate(PATH, lambda d: d["baseline_assemblers"].append("skesa"))
        self.mutate(PATH, lambda d: d.update(qualifying=True))
        self.mutate(PATH, lambda d: d["candidates"][0].update(qualifying=True))

    def test_reject_unpinned_execution_or_unsafe_limits(self):
        self.mutate(PATH, lambda d: d["candidates"][0].update(status="pilot"))
        self.mutate(PATH, lambda d: d["candidates"][0].update(status="proposed"))
        self.mutate(PATH, lambda d: d["policy"].update(total_incremental_storage_bytes=9*1024**3))
        self.mutate(PATH, lambda d: d["policy"].update(max_concurrent_exploratory_workers=2))

    def test_reject_duplicate_or_replacement(self):
        self.mutate(PATH, lambda d: d["candidates"][0].update(id="iva"))
        self.mutate(PATH, lambda d: d["candidates"][0].update(id=d["candidates"][1]["id"]))


if __name__ == "__main__":
    unittest.main()
