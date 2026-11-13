"""Incomplete diagnostics must be explicitly null, not stale or fabricated."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from assembler_bench.current_mapping import missing_arm, snapshot
from assembler_bench.site_build import SITE
from assembler_bench.site_validation import check_mapping_snapshot


class CurrentMappingTests(unittest.TestCase):
    def test_missing_complete_seven_arm_case_has_no_fabricated_diagnostics(self):
        tools = ("iva", "ivanka", "haploflow", "megahit",
                 "abyss", "spades", "velvet")
        run = {
            "id": "synthetic-run", "tools": tools,
            "samples": [{"alias": "H001"}],
            "images": {tool: f"{i+1:x}"*64 for i, tool in enumerate(tools)},
        }
        row = {"id": "case01", "results": {
            tool: {"status": "failed"} for tool in tools}}
        result = snapshot([row], run)
        self.assertEqual(result["cases_measured"], 0)
        self.assertIsNone(result["sample_alias"])
        self.assertEqual(set(result["tools"]), set(tools))
        for entry in result["tools"].values():
            self.assertEqual(entry, missing_arm())

    def test_public_zero_case_placeholder_is_valid_and_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            site=Path(directory)/"site"
            shutil.copytree(SITE,site)
            report=json.loads((site/"data/runs.json").read_text())
            run=next(r for r in report["runs"]
                     if r.get("hxb2_truth_verified"))
            from assembler_bench.current_mapping import catalog
            placeholder={
                "schema": "assembler-bench.public-mapping-diagnostics.v1",
                "run_id": run["id"], "sample_alias": None,
                "status": "INCOMPLETE", "cases_measured": 0,
                "expected_cases": 400,
                "cohort": "Source-attested HXB2-derived synthetic MiCall",
                "note": "No completed mapped case",
                "metric_catalog": catalog(),
                "tools": {tool:missing_arm() for tool in run["tools"]},
            }
            file=site/"data/mapping-diagnostics.json"
            file.write_text(json.dumps(placeholder))
            check_mapping_snapshot(site,report)
            broken=copy.deepcopy(placeholder)
            broken["tools"]["ivanka"]["values"]["soft_clipped_reads"]=0
            file.write_text(json.dumps(broken))
            with self.assertRaisesRegex(ValueError,"must be null"):
                check_mapping_snapshot(site,report)
            broken=copy.deepcopy(placeholder)
            broken["note"]="/workspace/private-path"
            file.write_text(json.dumps(broken))
            with self.assertRaisesRegex(ValueError,"private"):
                check_mapping_snapshot(site,report)


if __name__ == "__main__":
    unittest.main()
