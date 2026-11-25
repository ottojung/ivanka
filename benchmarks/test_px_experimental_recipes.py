"""Source-only PX recipes must stay pinned, bounded and nonqualifying."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import reference_isolation

from px_experimental_recipes import RECIPES, checked, checked_patch

NAMES = ("ray", "tadpole", "native-requirements", "ray-disk-admission-design")


class TestSourceOnlyRecipes(unittest.TestCase):
    def test_all_recipes_validate(self):
        for name in NAMES:
            with self.subTest(recipe=name):
                self.assertEqual(checked(name)["claim"], "measured-data-only")

    def test_patch_is_link_only(self):
        text = checked_patch()
        self.assertIn("SOAPdenovo-63mer", text)
        self.assertIn("SOAPdenovo-127mer", text)

    def test_no_private_paths_or_reference_flags(self):
        for path in RECIPES.glob("*.json"):
            body = path.read_text()
            self.assertNotIn("/workspace/", body)
            self.assertNotIn("/home/lubko/", body)
            self.assertNotIn("--reference", body)

    def test_pin_drift_is_rejected(self):
        original = json.loads((RECIPES / "ray-rayplatform-c8d9fe2.json").read_text())
        mutated = dict(original, adapter_commit="0" * 40)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ray-rayplatform-c8d9fe2.json"
            target.write_text(json.dumps(mutated))
            with mock.patch("px_experimental_recipes._document",
                            side_effect=lambda n: (mutated, target)):
                with self.assertRaises(ValueError):
                    checked("ray")

    def test_legacy_cap_field_is_accepted_and_ignored(self):
        document = json.loads((RECIPES / "tadpole-minimal-jre.json").read_text())
        document["resource_contract"] = dict(
            document["resource_contract"],
            max_incremental_bytes=32 * 1024**3)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "tadpole-minimal-jre.json"
            target.write_text(json.dumps(document))
            with mock.patch("px_experimental_recipes._document",
                            side_effect=lambda n: (document, target)):
                self.assertEqual(checked("tadpole")["claim"], "measured-data-only")

    def test_reserved_limits_still_reject_drift(self):
        document = json.loads((RECIPES / "tadpole-minimal-jre.json").read_text())
        document["resource_contract"] = dict(
            document["resource_contract"],
            min_free_bytes=16 * 1024**3)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "tadpole-minimal-jre.json"
            target.write_text(json.dumps(document))
            with mock.patch("px_experimental_recipes._document",
                            side_effect=lambda n: (document, target)):
                with self.assertRaises(ValueError):
                    checked("tadpole")

    def test_ray_design_preserves_historical_budget_evidence(self):
        # measured_budget records the earlier capped build attempts; cap_bytes
        # is historical evidence, not a live limit. Current build prose must
        # point at that field instead of asserting a 20 GiB build cap.
        document = json.loads(
            (RECIPES / "ray-disk-admission-design.json").read_text())
        budget = document["measured_budget"]
        self.assertEqual(budget["cap_bytes"], 21474836480)
        self.assertEqual(budget["reservation_bytes"], 1 << 30)
        self.assertEqual(len(document["attempts"]), 3)
        self.assertTrue(all("under the 20 GiB cap" not in option
                            for option in document["design_options"]))
        self.assertIn("measured_budget", document["design_options"][0])
        for change in (
                lambda d: d["measured_budget"].update(reservation_bytes=0),
                lambda d: d["measured_budget"].update(headroom_bytes=-1),
                lambda d: d.update(attempts=[])):
            with self.subTest(change=change):
                mutated = copy.deepcopy(document)
                change(mutated)
                with tempfile.TemporaryDirectory() as directory:
                    target = Path(directory) / "ray-disk-admission-design.json"
                    target.write_text(json.dumps(mutated))
                    with mock.patch("px_experimental_recipes._document",
                                    side_effect=lambda n, m=mutated, t=target:
                                    (m, t)):
                        with self.assertRaises(ValueError):
                            checked("ray-disk-admission-design")

    def test_compact_plans_for_remaining_tools(self):
        tools = checked("native-requirements")["tools"]
        for name in ("unicycler", "penguin", "savage-denovo"):
            self.assertTrue(tools[name]["compact_plan"])

    def test_reference_isolation_guard(self):
        self.assertEqual(reference_isolation.check_repository(), [])


if __name__ == "__main__":
    unittest.main()
