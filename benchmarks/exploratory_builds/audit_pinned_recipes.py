"""Recompute audited build args from pinned git objects (local audit tool).

Requires a MiCall fork checkout containing all pinned adapter commits. This is
an operator verification of recipe_audit.json, not a CI test or an OCI build.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from assembler_bench.exploratory_policy import checked

HERE = Path(__file__).resolve().parent
REGISTRY = HERE.parent / "assembler_bench" / "exploratory_candidates.json"


def git_blob(checkout, commit, path):
    result = subprocess.run(
        ["git", "-C", str(checkout), "show", commit + ":" + path],
        check=True, capture_output=True, timeout=60)
    return hashlib.sha256(result.stdout).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fork-checkout", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=None)
    parser.add_argument("--binary-tool", default="skesa")
    args = parser.parse_args()

    audit = json.loads((HERE / "recipe_audit.json").read_text())
    registry = checked(REGISTRY)
    failures = []
    for tool, recipe in sorted(audit["recipes"].items()):
        commit = registry["adapter_branch_commits"][tool]
        for name, filename in (
                ("adapter_commands_sha256", "micall/core/assembler_commands.py"),
                ("adapter_dispatch_sha256", "micall/core/assembler_dispatch.py")):
            actual = git_blob(args.fork_checkout, commit, filename)
            if actual != recipe[name]:
                failures.append("%s %s expected %s got %s"
                                % (tool, name, recipe[name], actual))
        print("%s adapter args OK at %s" % (tool, commit[:12]))
    if args.binary is not None:
        digest = hashlib.sha256(args.binary.read_bytes()).hexdigest()
        expected = audit["recipes"][args.binary_tool]["attested_binary_sha256"]
        if digest != expected:
            failures.append("binary digest %s != %s" % (digest, expected))
        else:
            print("%s native binary digest OK" % args.binary_tool)
    if failures:
        raise SystemExit("AUDIT FAILED:\n" + "\n".join(failures))
    print("AUDIT PASS: pinned adapter build args match git objects")


if __name__ == "__main__":
    main()
