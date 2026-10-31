import unittest
from pathlib import Path
from .lines import effective_lines, python_lines, rust_lines, crowded

class EffectiveLineTests(unittest.TestCase):
    def test_python_comments_and_strings(self):
        text = '# comment\nx = "# not a comment" # inline\n\n# tail\ny = 2\n'
        self.assertEqual(python_lines(text), 2)

    def test_rust_nested_comments_and_urls(self):
        text = '/* outer\n/* inner */\nend */\nlet url = "https://example.org"; // note\n'
        self.assertEqual(rust_lines(text), 1)

    def test_shell_comments(self):
        self.assertEqual(effective_lines(Path("a.sh"), "#!/bin/sh\n# hi\necho hi\n"), 1)

    def test_limit_is_strict(self):
        self.assertEqual(python_lines("x = 1\n" * 50), 50)
        self.assertEqual(python_lines("x = 1\n" * 51), 51)

    def test_python_packed_statements(self):
        self.assertEqual(crowded(Path("a.py"), "a=1; b=2\n"), [1])
        self.assertEqual(crowded(Path("a.py"), "a=1\nb=2\n"), [])

    def test_rust_packed_statements(self):
        self.assertEqual(crowded(Path("a.rs"), "let a=1; let b=2;\n"), [1])
        self.assertEqual(crowded(Path("a.rs"), 'let s="x;y";\n'), [])
