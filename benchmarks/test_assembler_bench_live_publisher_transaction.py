"""Prove a failed Pages publication cannot poison a later retry."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parent / "assembler_bench/live_publish_loop.sh"


def run(*cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, text=True,
                          capture_output=True, timeout=25)


class TransactionalPagesTests(unittest.TestCase):
    def test_failed_validation_and_rejected_push_leave_no_partial_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo, remote = root/"source", root/"origin.git"
            repo.mkdir()
            self.assertEqual(run("git", "init", "-q", "-b", "main",
                                 str(repo)).returncode, 0)
            self.assertEqual(run("git", "init", "-q", "--bare", "-b",
                                 "main", str(remote)).returncode, 0)
            for key, value in (("user.name", "Benchmark Publisher Test"),
                               ("user.email", "publisher@test.invalid")):
                self.assertEqual(run("git", "-C", str(repo),
                                     "config", key, value).returncode, 0)
            (repo/"benchmarks/assembler_bench").mkdir(parents=True)
            (repo/"site/bench/data").mkdir(parents=True)
            for path in ("benchmarks/__init__.py",
                         "benchmarks/assembler_bench/__init__.py",
                         "site/bench/data/mapping-diagnostics.json",
                         "site/bench/data/live-fork-attestation.json"):
                item = repo/path
                item.parent.mkdir(parents=True, exist_ok=True)
                item.write_text("{}")
            record = repo/"site/bench/data/runs.json"
            record.write_text('{"value":"previous"}')
            (repo/"benchmarks/assembler_bench/live_progress.py").write_text(
                "from pathlib import Path\n"
                "import os\n"
                "Path('site/bench/data/runs.json').write_text("
                "'{\"value\":\"new\"}')\n"
                "if os.getenv('PUBLISH_TEST_FAIL'): "
                "raise RuntimeError('injected validation failure')\n")
            commands = [
                ("git", "-C", str(repo), "add", "."),
                ("git", "-C", str(repo), "commit", "-qm", "baseline"),
                ("git", "-C", str(repo), "remote", "add", "origin", str(remote)),
                ("git", "-C", str(repo), "push", "-q", "origin", "main"),
            ]
            for command in commands:
                result = run(*command)
                self.assertEqual(result.returncode, 0, result.stderr)
            env = dict(os.environ)
            env.update(IVANKA_BENCH_CHECKOUT=str(repo),
                       IVANKA_BENCH_FORK="test",
                       IVANKA_BENCH_FORK_RUNNER="test",
                       IVANKA_BENCH_REAL="test",
                       IVANKA_BENCH_REAL_DATA="test",
                       IVANKA_BENCH_ATTESTATION="test",
                       IVANKA_BENCH_FORK_REPO="test",
                       IVANKA_BENCH_BASE="test",
                       IVANKA_BENCH_INTERVAL="60",
                       IVANKA_BENCH_ONCE="1", TMPDIR=str(root))
            original = record.read_bytes()

            def attempt(expected):
                outcome = run("sh", str(SCRIPT), env=env)
                self.assertEqual(outcome.returncode == 0, expected,
                                 outcome.stdout + outcome.stderr)
                checkout = run("git", "-C", str(repo), "worktree", "list",
                               "--porcelain")
                self.assertEqual(checkout.returncode, 0, checkout.stderr)
                self.assertEqual(checkout.stdout.count("worktree "), 1)
                return outcome

            env["PUBLISH_TEST_FAIL"] = "1"
            first = attempt(False)
            self.assertNotIn("LIVE_PAGES_PUSHED", first.stdout)
            self.assertEqual(record.read_bytes(), original)
            env.pop("PUBLISH_TEST_FAIL")
            hook = remote/"hooks/pre-receive"
            hook.write_text("#!/bin/sh\nexit 1\n")
            hook.chmod(0o755)
            rejected = attempt(False)
            self.assertNotIn("LIVE_PAGES_PUSHED", rejected.stdout)
            self.assertEqual(record.read_bytes(), original)
            hook.unlink()
            succeeded = attempt(True)
            self.assertIn("LIVE_PAGES_PUSHED", succeeded.stdout)
            self.assertEqual(record.read_bytes(), original)
            committed = run("git", "--git-dir", str(remote), "show",
                            "main:site/bench/data/runs.json")
            self.assertEqual(committed.returncode, 0, committed.stderr)
            self.assertEqual(committed.stdout, '{"value":"new"}')
