import tempfile
import unittest
from pathlib import Path
from .python_deps import violations as py
from .rust_deps import violations as rust
from .shell_deps import violations as shell

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / "src"
        self.directory.mkdir()
        (self.directory / "peer.py").write_text("value = 1\n")
        (self.directory / "peer.rs").write_text("pub fn f() {}\n")
        (self.directory / "peer.sh").write_text("true\n")
        (self.directory / "pkg").mkdir()
        (self.directory / "pkg" / "deep.py").write_text("pass\n")
        (self.directory / "pkg" / "deep.rs").write_text("pub fn f() {}\n")

    def test_python_sibling_and_external(self):
        path = self.directory / "a.py"
        self.assertEqual(py(path, "import peer\nfrom Bio.Seq import Seq\n", self.root), [])
        self.assertTrue(py(path, "from pkg.deep import x\n", self.root))
        self.assertTrue(py(path, "from pkg import deep\n", self.root))
        self.assertTrue(py(path, "from ..peer import value\n", self.root))
        self.assertTrue(py(path, 'exec("x=1")\n', self.root))
        self.assertTrue(py(path, 'importlib.import_module("peer")\n', self.root))

    def test_rust_sibling_and_descendant(self):
        path = self.directory / "a.rs"
        self.assertEqual(rust(path, "mod peer;\nuse super::peer::f;\n", self.root), [])
        self.assertTrue(rust(path, "use super::pkg::deep::f;\n", self.root))
        self.assertTrue(rust(path, "use crate::pkg::deep;\n", self.root))
        self.assertTrue(rust(path, "use pkg::deep::f;\n", self.root))
        self.assertTrue(rust(path, 'include!("generated.rs");\n', self.root))
        self.assertEqual(rust(path, "// use crate::pkg::deep;\n", self.root), [])

    def test_shell_sibling_and_parent(self):
        path = self.directory / "a.sh"
        self.assertEqual(shell(path, ". ./peer.sh\n", self.root), [])
        self.assertTrue(shell(path, ". ../peer.sh\n", self.root))
        self.assertTrue(shell(path, "source $DYNAMIC\n", self.root))
