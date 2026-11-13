"""Live publication keeps stable IDs, unmodified cohorts, and failures visible."""
import copy
import json
import unittest

from assembler_bench.live_progress import LEGACY_ID, FORK_ID, replace_run
from assembler_bench.site_build import SITE, validate_public_site


class LiveProgressTests(unittest.TestCase):
    def test_stable_progress_and_monotone_evidence(self):
        run = {"id": FORK_ID, "sample_count": 3, "images": {"ivanka": "a" * 64}}
        next_run = {**run, "sample_count": 4}
        self.assertEqual(replace_run([run], next_run), [next_run])
        with self.assertRaisesRegex(ValueError, "regressed"):
            replace_run([next_run], run)
        with self.assertRaisesRegex(ValueError, "images"):
            replace_run([run], {**next_run, "images": {}})

    def test_multiple_runs_stay_separate(self):
        first = {"id": LEGACY_ID, "sample_count": 20, "images": {}}
        second = {"id": FORK_ID, "sample_count": 4, "images": {}}
        self.assertEqual([x["id"] for x in replace_run(
            replace_run([], first), second)], [LEGACY_ID, FORK_ID])

    def test_source_provenance_is_not_silently_rewritten(self):
        from assembler_bench.public_dominance import enrich
        report = json.loads((SITE / "data/runs.json").read_text())
        verified = copy.deepcopy(report["runs"][-1])
        verified["id"] = FORK_ID
        verified["micall_fork_provenance"] = {
            "status": "verified", "message": "independently verified"}
        report["runs"].append(verified)
        result = enrich(report)
        self.assertEqual(result["runs"][-1]["micall_fork_provenance"],
                         verified["micall_fork_provenance"])

    def test_browser_reloads_only_when_visitor_refreshes(self):
        js = (SITE / "app.js").read_text()
        self.assertIn('fetch("./data/runs.json",{cache:"no-store"})', js)
        for keyword in ("setInterval(", "setTimeout(", "EventSource(",
                        "WebSocket(", "pollProgress"):
            self.assertNotIn(keyword, js)

    def test_existing_snapshot_still_passes_validation(self):
        self.assertGreaterEqual(validate_public_site(SITE), 3)


if __name__ == "__main__":
    unittest.main()
