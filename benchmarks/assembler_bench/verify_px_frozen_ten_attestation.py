"""Fail-closed verifier for the ten frozen-8458f9e5 PX adapter attestations.

Recomputes native artifact digests from preserved files and adapter module
digests from pinned MiCall git objects. Never accepts a missing measurement, a
missing file or a wrong parent commit as a pass. No image, pilot or score is
claimed by this module.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

MANIFEST = Path(__file__).with_name("px_frozen_ten_attestation.json")
HEX = set("0123456789abcdef")
MODULES = (
    ("adapter_commands_sha256", "micall/core/benchmark_assembler.py"),
    ("adapter_denovo_sha256", "micall/core/denovo.py"),
)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _expected(value):
    return (isinstance(value, str) and len(value) == 64
            and set(value.lower()) <= HEX)


def _scoped(root, relative):
    base = Path(root).resolve()
    parts = Path(relative).parts
    if not parts or parts[0] == "/":
        raise ValueError("artifact outside the declared root")
    current = base
    for part in parts:
        current = current / part
        # Check the link itself before resolution: a symlink to an in-root
        # file is still not the attested artifact and must fail closed.
        if current.is_symlink():
            raise ValueError("artifact outside the declared root")
    path = current.resolve()
    if not path.is_relative_to(base):
        raise ValueError("artifact outside the declared root")
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path


def verify_native(manifest, workspace_root):
    """Return one result per native artifact; any error is a failed result."""
    results = []
    for tool, row in sorted(manifest["tools"].items()):
        try:
            path = _scoped(workspace_root, row["native_artifact"])
            actual = sha256_file(path)
            results.append({"tool": tool, "kind": "native",
                            "ok": actual == row["native_sha256"],
                            "expected": row["native_sha256"],
                            "actual": actual})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            results.append({"tool": tool, "kind": "native", "ok": False,
                            "reason": f"{type(exc).__name__}: {exc}"})
    return results


def _git(checkout, *argv):
    return subprocess.run(["git", "-C", str(checkout), *argv],
                          capture_output=True, check=True).stdout


def verify_adapters(manifest, micall_checkout):
    """Recompute module digests and the frozen parent from pinned git objects."""
    results = []
    frozen = manifest["frozen_upstream_master"]
    for tool, row in sorted(manifest["tools"].items()):
        pin = row["adapter_commit"]
        try:
            parent = _git(micall_checkout, "rev-parse", pin + "^").decode().strip()
            if parent != frozen:
                raise ValueError(f"adapter parent {parent} != frozen master")
            for field, relpath in MODULES:
                data = _git(micall_checkout, "show", f"{pin}:{relpath}")
                actual = sha256_bytes(data)
                results.append({"tool": tool, "kind": relpath,
                                "ok": actual == row[field],
                                "expected": row[field], "actual": actual})
        except (OSError, ValueError, KeyError, TypeError,
                subprocess.SubprocessError) as exc:
            results.append({"tool": tool, "kind": "adapter", "ok": False,
                            "reason": f"{type(exc).__name__}: {exc}"})
    return results


def verify(manifest, workspace_root, micall_checkout):
    if not _expected(manifest.get("frozen_seven_manifest_sha256")):
        raise ValueError("manifest missing frozen seven digest")
    if len(manifest.get("tools", {})) != 10:
        raise ValueError("manifest must cover exactly ten tools")
    return verify_native(manifest, workspace_root) + verify_adapters(
        manifest, micall_checkout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--micall-checkout", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text())
        results = verify(manifest, args.workspace_root, args.micall_checkout)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}, sort_keys=True))
        return 2
    passed = sum(1 for item in results if item["ok"])
    report = {"ok": passed == len(results), "passed": passed,
              "checked": len(results), "results": results}
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
