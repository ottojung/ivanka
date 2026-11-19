import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from .synthetic_scan import name_from_args, summary


class SyntheticScanTests(unittest.TestCase):
    def test_name_from_args(self):
        self.assertEqual(name_from_args(["run", "--name=a", "img"]), "a")
        self.assertEqual(name_from_args(["run", "--name", "b", "img"]), "b")

    def test_existing_success_without_cap_is_not_qualified(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            output = root / "phase-synthetic464" / "case-001" / "spades"
            output.mkdir(parents=True)
            record = {"status": "success", "container_wall_seconds": 8,
                      "argv": ["podman", "run", "--name", "container-1"]}
            (output / "execution.json").write_text(json.dumps(record))
            tele = {"container-1": {"peak_tree_rss_bytes_sampled": 1000}}
            self.assertEqual(summary(root, tele, {})["spades"],
                             {"legacy_uncapped": 1})
