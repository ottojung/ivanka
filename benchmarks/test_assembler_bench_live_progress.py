"""Live publication keeps stable IDs, unmodified cohorts, and failures visible."""
import copy
import json
import unittest

from assembler_bench.live_progress import FORK_ID, replace_run
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
        first = {"id": FORK_ID, "sample_count": 4, "images": {}}
        second = {"id": "real198-fork-source-attested-live",
                  "sample_count": 20, "images": {}}
        self.assertEqual([x["id"] for x in replace_run(
            replace_run([], first), second)], [FORK_ID, second["id"]])

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

    def test_new_immutable_image_set_can_reset_checkpoint_counts(self):
        from assembler_bench.live_progress import replace_run
        old = {"id": FORK_ID, "sample_count": 400,
               "images": {"iva": "a" * 64}}
        replacement = {
            "id": "hxb2-v4-dedicated-source-live", "sample_count": 0,
            "images": {"iva": "b" * 64}}
        self.assertEqual(replace_run([], replacement), [replacement])
        self.assertEqual(replace_run([old], replacement),
                         [old, replacement])
        with self.assertRaisesRegex(ValueError, "regressed"):
            replace_run([replacement], {**replacement, "sample_count": -1})

    def test_browser_reloads_only_when_visitor_refreshes(self):
        js = (SITE / "app.js").read_text()
        self.assertIn('fetch("./data/runs.json",{cache:"no-store"})', js)
        for keyword in ("setInterval(", "setTimeout(", "EventSource(",
                        "WebSocket(", "pollProgress"):
            self.assertNotIn(keyword, js)

    def test_publisher_uses_one_verified_checkpoint_for_report_and_mapping(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from assembler_bench import live_progress

        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)/"site"
            data = site/"data"
            data.mkdir(parents=True)
            (data/"runs.json").write_text('{"runs":[]}')
            (data/"mapping-diagnostics.json").write_text("{}")
            att = Path(directory)/"attestation.json"
            att.write_text("{}")
            rows = [{"id": "a"}, {"id": "b"}]
            verified = ({"images": {}}, rows, "digest", {})
            run = {"id": FORK_ID, "cohort": "synthetic",
                   "sample_count": 2, "images": {},
                   "micall_fork_provenance": {}}
            progress = {"candidates": {"ivanka": {"finished": 0}}}
            with (patch.object(live_progress, "checked_fork",
                               return_value=verified) as checked,
                  patch.object(live_progress, "fork_preview",
                               return_value=run) as preview,
                  patch.object(live_progress, "real_snapshot",
                               return_value=progress),
                  patch.object(live_progress, "physical_preview",
                               return_value={"id": "real"}),
                  patch.object(live_progress, "combined_preview",
                               return_value={"id": "combined"}),
                  patch.object(live_progress, "enrich",
                               side_effect=lambda x: x),
                  patch.object(live_progress, "mapping_snapshot",
                               return_value={}) as mapping,
                  patch.object(live_progress, "validate_public_site")):
                live_progress.update(
                    site, "fork", "runner", att, "sources", "base",
                    real="real", real_data="physical")
                checked.assert_called_once()
                self.assertIs(preview.call_args.kwargs["checked_result"],
                              verified)
                self.assertIs(mapping.call_args.args[0], rows)
                self.assertEqual(
                    json.loads((data/"runs.json").read_text())["runs"][0], run)

    def test_verified_preview_never_reloads_a_new_checkpoint_generation(self):
        from unittest.mock import patch
        from assembler_bench import fork_progress
        verified = (
            {"images": {"iva": "a"*64}, "truth_proof": {},
             "benchmark_source_sha256": {}},
            [{"id": "clonal-s000"}], "b"*64,
            {"schema": "test", "base_image_sha256": "c"*64,
             "images": {"iva": {"source_commit": "a"*40,
                               "source_url": "https://example.org",
                               "image_sha256": "a"*64}}})
        with (patch.object(fork_progress, "checked",
                           side_effect=AssertionError("second checkpoint read")),
              patch.object(fork_progress, "format_preview",
                           return_value={"sample_count": 1, "samples": [],
                                     "tools": []}) as formatter,
              patch.object(fork_progress, "sha", return_value="d"*64),
              patch.object(fork_progress.subprocess, "check_output",
                           return_value="e"*40)):
            run = fork_progress.preview(
                "run", "runner", "att", "fork", "base",
                checked_result=verified)
        self.assertEqual(run["sample_count"], 1)
        self.assertEqual(formatter.call_args.args[1],
                         verified[1])

    def test_existing_snapshot_still_passes_validation(self):
        self.assertGreaterEqual(validate_public_site(SITE), 3)


if __name__ == "__main__":
    unittest.main()
