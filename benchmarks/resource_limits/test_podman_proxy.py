import unittest
from .podman_args import capped, option, CAP_BYTES, PODMAN_TIMEOUT


class ProxyTests(unittest.TestCase):
    def test_physical_create(self):
        argv = ["create", "--name", "ivanka-bench-ivanka-retry-foo",
                "--timeout", "2997", "image", "micall"]
        result, yes = capped(argv)
        self.assertTrue(yes)
        self.assertEqual(option(result, "--timeout")[1], str(PODMAN_TIMEOUT))
        self.assertEqual(option(result, "--memory")[1], str(CAP_BYTES))
        self.assertEqual(option(result, "--memory-swap")[1], str(CAP_BYTES))
        self.assertEqual(result[-2:], ["image", "micall"])

    def test_synthetic_run_reduces_five_gib(self):
        result, yes = capped(["run", "--name=ivanka-bench-synth-x",
                              "--timeout", "3000", "--memory=5g", "image"])
        self.assertTrue(yes)
        self.assertEqual(option(result, "--memory")[1], str(CAP_BYTES))
        self.assertEqual(option(result, "--timeout")[1], str(PODMAN_TIMEOUT))

    def test_smaller_timeout_stays_smaller(self):
        result, _ = capped(["create", "--name", "ivanka-bench-iva-smoke",
                            "--timeout", "100", "image"])
        self.assertEqual(option(result, "--timeout")[1], "100")

    def test_other_project_is_transparent(self):
        cmd = ["create", "--name", "skrynia-thing", "--timeout", "100"]
        self.assertEqual(capped(cmd), (cmd, False))
        cmd = ["image", "inspect", "digest"]
        self.assertEqual(capped(cmd), (cmd, False))

    def test_reject_missing_benchmark_timeout(self):
        with self.assertRaises(ValueError):
            capped(["run", "--name", "ivanka-bench-test", "image"])

    def test_reject_duplicate_benchmark_options(self):
        with self.assertRaises(ValueError):
            capped(["create", "--name=x", "--name=y", "--timeout=3000"])
