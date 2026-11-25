"""Source-only PX recipes must stay pinned, bounded and nonqualifying."""
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

    def test_compact_plans_for_remaining_tools(self):
        tools = checked("native-requirements")["tools"]
        for name in ("unicycler", "penguin", "savage-denovo"):
            self.assertTrue(tools[name]["compact_plan"])

    def test_reference_isolation_guard(self):
        self.assertEqual(reference_isolation.check_repository(), [])


if __name__ == "__main__":
    unittest.main()
