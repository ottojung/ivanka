import tempfile
import unittest
from pathlib import Path
from .files import fanout, tracked

class TrackedFilesTests(unittest.TestCase):
    def test_directory_entries_include_subdirectories(self):
        paths = [Path("a") / f"file{i}.py" for i in range(9)]
        paths += [Path("a/b/c.py"), Path("a/d/e.py")]
        counts = dict(fanout(paths))
        self.assertEqual(counts["a"], 11)
        self.assertEqual(counts["."], 1)
        self.assertEqual(counts["a/b"], 1)

    def test_git_tracked_and_unignored(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "one.py").write_text("pass\n")
            (root / ".gitignore").write_text("ignored.py\n")
            (root / "ignored.py").write_text("pass\n")
            names = tracked(root)
            self.assertIn(Path("one.py"), names)
            self.assertNotIn(Path("ignored.py"), names)
