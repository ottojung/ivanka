import json
import tempfile
import unittest
from pathlib import Path
from archive_finished_benchmarks import terminal_artifacts, read_records


class ArchiveFinishedTests(unittest.TestCase):
    def test_only_terminal_valid_internal_arms(self):
        with tempfile.TemporaryDirectory() as x:
            root = Path(x)
            for name in ("done/iva/scratch", "done/ivanka/scratch",
                         "active/iva/scratch"):
                (root/name).mkdir(parents=True)
            records = [
                {"status": "started", "iva": {"artifact_dir": str(root/"active/iva")}},
                {"status": "finished", "iva": {"artifact_dir": str(root/"done/iva")},
                 "ivanka": {"artifact_dir": str(root/"done/ivanka")}},
            ]
            got = terminal_artifacts(root, records)
            self.assertEqual(len(got), 2)
            self.assertNotIn((root/"active/iva").resolve(), got)

    def test_refuse_external_artifact_path(self):
        with tempfile.TemporaryDirectory() as x:
            with tempfile.TemporaryDirectory() as y:
                (Path(y)/"scratch").mkdir()
                records=[{"status":"finished","iva":{"artifact_dir":y}}]
                with self.assertRaises(ValueError):
                    terminal_artifacts(x,records)

    def test_partial_last_record_does_not_interrupt_watcher(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "results.jsonl"
            path.write_text(json.dumps({"status": "finished"}) + "\n{\"status\":")
            self.assertEqual(read_records(path), [{"status": "finished"}])
            path.write_text(path.read_text() + '\"finished\"}\n')
            self.assertEqual(len(read_records(path)), 2)

    def test_record_parser_handles_appended_jsonl(self):
        with tempfile.TemporaryDirectory() as x:
            p=Path(x)/"results.jsonl"
            p.write_text(json.dumps({"status":"started"})+"\n"+json.dumps({"status":"finished"})+"\n")
            self.assertEqual(len(read_records(p)),2)
