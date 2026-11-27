"""Focused checks for staged PX readiness-recipe binary attestation.

A staged readiness recipe that records ``TOOL_BINARY_SHA256`` only as an OCI
label does not attest anything about the artifact inside the image: any
supplied digest would be accepted.  These checks require the PenguiN staged
recipe to enforce the digest against the installed binary with ``sha256sum``
and prove, by executing the very shell expression from the recipe, that a
wrong digest or a tampered binary fails closed (non-zero exit).
"""
import hashlib
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPE = (
    ROOT / "docs" / "bench" / "px-source-readiness-20261126"
    / "Dockerfile.assembler-bench.penguin.corrected"
)
BINARY = "/usr/local/bin/penguin"
VAR = "${TOOL_BINARY_SHA256}"


def recipe_text():
    return RECIPE.read_text(encoding="utf-8")


def enforcement_statement(text):
    """Return the complete multi-line RUN statement that verifies the binary."""
    statements, current = [], []
    for line in text.splitlines():
        if current:
            current.append(line)
            if not line.rstrip().endswith("\\"):
                statements.append(current)
                current = []
        elif line.lstrip().startswith("RUN "):
            current = [line]
    matches = [statement for statement in statements
               if any("sha256sum -c" in line and VAR in line and BINARY in line
                      for line in statement)]
    if len(matches) != 1:
        raise AssertionError(
            "expected exactly one in-image sha256sum enforcement of %s against "
            "%s, found %d" % (VAR, BINARY, len(matches)))
    return matches[0]


def shell_expression(statement):
    """Turn a Dockerfile RUN statement into an executable /bin/sh expression."""
    joined = "\n".join(statement)
    expr = re.sub(r"\\\s*\n", " ", joined).strip()
    expr = re.sub(r"^RUN\s+", "", expr)
    return expr


def run_verification(expr, digest, binary_path):
    command = expr.replace(VAR, digest).replace(BINARY, str(binary_path))
    env = dict(os.environ)
    return subprocess.run(["/bin/sh", "-c", command], env=env,
                          capture_output=True, text=True, timeout=30)


class StagedBinaryAttestationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = recipe_text()
        cls.statement = enforcement_statement(cls.text)
        cls.expr = shell_expression(cls.statement)

    def test_recipe_is_not_label_only(self):
        """The digest must be checked in-image, not merely labelled."""
        labels = [line for line in self.text.splitlines()
                  if "tool-binary-sha256" in line and line.startswith("LABEL")]
        self.assertTrue(labels, "expected a provenance label for the digest")
        self.assertIn(VAR, "\n".join(self.statement))

    def test_enforcement_targets_installed_binary(self):
        self.assertIn(BINARY, self.expr)
        self.assertIn("sha256sum -c", self.expr)

    def test_correct_digest_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "penguin"
            binary.write_bytes(b"genuine-penguin-binary-content\n")
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            result = run_verification(self.expr, digest, binary)
            self.assertEqual(result.returncode, 0,
                             "correct digest must pass: " + result.stdout
                             + result.stderr)

    def test_wrong_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "penguin"
            binary.write_bytes(b"genuine-penguin-binary-content\n")
            wrong = "0" * 64
            self.assertNotEqual(
                wrong, hashlib.sha256(binary.read_bytes()).hexdigest())
            result = run_verification(self.expr, wrong, binary)
            self.assertNotEqual(
                result.returncode, 0,
                "a wrong TOOL_BINARY_SHA256 must abort the build")

    def test_tampered_binary_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "penguin"
            binary.write_bytes(b"genuine-penguin-binary-content\n")
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            binary.write_bytes(b"tampered-penguin-binary-content\n")
            result = run_verification(self.expr, digest, binary)
            self.assertNotEqual(
                result.returncode, 0,
                "a binary modified after attestation must abort the build")


if __name__ == "__main__":
    unittest.main()
