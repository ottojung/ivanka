"""Upstream cfe-lab/MiCall stays fetch-only regardless of Git transport."""
import unittest

from assembler_bench.micall_source_guard import (
    fork_commit_url, repo_name, require_fork_write_destination,
    validate_fork_image_manifest,
)


class MiCallForkGuardTests(unittest.TestCase):
    def test_upstream_is_rejected_across_git_transport_forms(self):
        upstream = (
            "cfe-lab/MiCall",
            "https://github.com/cfe-lab/MiCall",
            "https://github.com/cfe-lab/MiCall.git",
            "git@github.com:cfe-lab/MiCall.git",
            "ssh://git@github.com/cfe-lab/MiCall.git",
            "GITHUB.COM/CFE-LAB/MICALL",
        )
        for remote in upstream:
            with self.subTest(remote=remote):
                self.assertEqual(repo_name(remote), "cfe-lab/micall")
                with self.assertRaisesRegex(ValueError, "refusing"):
                    require_fork_write_destination(remote)

    def test_only_ottojung_fork_accepted_as_write_destination(self):
        for url in (
            "ottojung/MiCall", "https://github.com/ottojung/MiCall.git",
            "git@github.com:ottojung/MiCall.git",
            "ssh://git@github.com/ottojung/MiCall.git",
        ):
            self.assertEqual(require_fork_write_destination(url),
                             "ottojung/micall")
        for url in ("https://example.org/ottojung/MiCall",
                    "github.com/ottojung/ivanka",
                    "https://github.com.evil.test/ottojung/MiCall",
                    "ottojung/MiCall/more"):
            with self.assertRaises(ValueError):
                require_fork_write_destination(url)

    def test_exact_fork_commits_not_moving_branches(self):
        sha = "a"*40
        self.assertEqual(fork_commit_url(sha),
                         "https://github.com/ottojung/MiCall/tree/"+sha)
        for bad in ("main", "a"*7, "A"*40, "0"*39+"g", "", None):
            with self.assertRaises(ValueError):
                fork_commit_url(bad)

    def test_manifest_requires_exact_fork_image_and_independent_attestation(self):
        sha,base = "a"*40,"b"*40
        correct = {
            "source_repository": "https://github.com/ottojung/MiCall",
            "source_commit": sha, "baseline_commit": base,
            "source_url": fork_commit_url(sha),
            "baseline_url": fork_commit_url(base),
            "image_sha256": "f"*64,
            "dockerfile_sha256": "e"*64,
            "oci_labels": {
                "org.opencontainers.image.source":
                    "https://github.com/ottojung/MiCall",
                "org.opencontainers.image.revision": sha,
            },
            "independently_verified_build": True,
        }
        self.assertTrue(validate_fork_image_manifest(correct))
        for key,value in (
            ("source_repository", "cfe-lab/MiCall"),
            ("source_url", "https://github.com/cfe-lab/MiCall/tree/"+sha),
            ("source_commit", "main"),
            ("baseline_url", "https://github.com/ottojung/MiCall/tree/main"),
            ("image_sha256", None),
            ("independently_verified_build", False),
        ):
            bad = dict(correct, **{key:value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_fork_image_manifest(bad)


if __name__ == "__main__":
    unittest.main()
