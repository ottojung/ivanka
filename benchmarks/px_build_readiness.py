"""Fail-closed readiness audit for hosted PX explorer builds.

This module never builds, pushes or executes an image. It decides whether a
*proposed* PX adapter checkout could even be considered for a future hosted
build. The current ten adapter branches are pinned to the eeca0381... lineage,
which diverges from the frozen MiCall base (8458f9e5...) across shared clinical
mapping code; building from them would be scientifically incomparable. A
candidate must instead be rebased onto the frozen base and carry an exact
shared-source attestation. ``builds_permitted`` is always False here: builds,
pushes and pilots require a separate future decision with real prerequisites.
"""
import argparse
import json
import re
from pathlib import Path

from assembler_bench import frozen_contract
from assembler_bench.exploratory_policy import EXPERIMENTAL, checked
from assembler_bench.fork_image_attestation import FORK_FILES
from assembler_bench.micall_source_guard import fork_commit_url, repo_name

BENCHMARKS = Path(__file__).resolve().parent
REGISTRY = BENCHMARKS / "assembler_bench" / "exploratory_candidates.json"
SCHEMA = "ivanka.px.shared-source-attestation.v1"
CANONICAL_FORK = "ottojung/micall"
SHA64 = re.compile(r"[a-f0-9]{64}\Z")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
DIGEST = re.compile(r"sha256:[a-f0-9]{64}\Z")
PERSISTENCE = frozenset(("ghcr-by-digest", "oci-artifact"))

# No reference genome, panel or evaluator score may steer an exploratory build.
# The guard matches the one used by the build-plan and hosted design documents.
FORBIDDEN = re.compile(
    r"(?i)(?:\bhxb2\b|reference[_-]?(?:panel|genome|fasta|catalog|truth)"
    r"|benchmark[_-]?panel|alignment[_-]?score|iva[_-]?score"
    r"|--(?:reference|ref|panel)(?:\b|=))"
)

FIELDS = ("tool", "adapter_repo", "adapter_commit", "base_commit",
          "attestation_path", "common_base_digest", "image_persistence")


def _no_reference(value, field):
    """Reject reference/truth material anywhere in a submitted request."""
    if isinstance(value, str):
        found = FORBIDDEN.search(value)
        if found:
            raise ValueError("reference material in " + field + ": " + found.group())
    elif isinstance(value, dict):
        for key, item in value.items():
            _no_reference(key, field)
            _no_reference(item, field)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _no_reference(item, field)


def _sha(value, pattern, field):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError("invalid " + field)
    return value


def load_attestation(path):
    """Load a shared-source attestation without trusting its claims."""
    data = json.loads(Path(path).read_text())
    if data.get("schema") != SCHEMA:
        raise ValueError("unsupported shared-source attestation schema")
    return data


def audit(inputs, registry_path=REGISTRY):
    """Return a readiness report; never authorize or perform a build."""
    for field in FIELDS:
        if field not in inputs:
            raise ValueError("missing readiness input: " + field)
    request = dict(inputs)
    attestation = load_attestation(request["attestation_path"])
    _no_reference(request, "readiness request")
    _no_reference(attestation, "shared-source attestation")

    registry = checked(registry_path)
    tool = request["tool"]
    if tool not in EXPERIMENTAL:
        raise ValueError("unknown or non-exploratory tool: " + str(tool))
    row = next(x for x in registry["candidates"] if x["id"] == tool)
    if (row["status"] != "source-pinned" or row["image_sha256"] is not None
            or row["qualifying"] is not False):
        raise ValueError("tool is not source-pinned and nonqualifying: " + tool)

    blockers = []
    if repo_name(request["adapter_repo"]) != CANONICAL_FORK:
        raise ValueError("adapter source is not canonical ottojung/MiCall")
    adapter = _sha(request["adapter_commit"], SHA40, "adapter_commit")
    old = set(registry["adapter_branch_commits"].values())
    if adapter in old:
        blockers.append(
            "old eeca0381-lineage PX adapter branch: scientifically "
            "incomparable to frozen seven; rebase required")
    base = request["base_commit"]
    if base != frozen_contract.COMMIT:
        blockers.append("adapter base is not the frozen MiCall commit")

    if attestation.get("source_commit") != adapter:
        blockers.append("attestation does not name the submitted adapter commit")
    if attestation.get("baseline_commit") != frozen_contract.COMMIT:
        blockers.append("attestation baseline is not the frozen MiCall commit")
    if attestation.get("source_url") != fork_commit_url(adapter):
        blockers.append("attestation source provenance link drifted")
    if attestation.get("baseline_url") != fork_commit_url(frozen_contract.COMMIT):
        blockers.append("attestation baseline provenance link drifted")
    if attestation.get("frozen_tree") != frozen_contract.TREE:
        blockers.append("attestation does not bind the frozen source tree")
    if attestation.get("frozen_manifest_sha256") != frozen_contract.MANIFEST:
        blockers.append("attestation does not bind the frozen seven manifest")
    if attestation.get("independently_verified") is not True:
        blockers.append("shared-source attestation is not independently verified")
    if attestation.get("denovo_calls_environment_dispatcher") is not False:
        blockers.append(
            "frozen denovo.py dispatcher behavior not attested: frozen source "
            "does not call the environment dispatcher")
    shared = attestation.get("shared_files")
    if (not isinstance(shared, dict) or set(shared) != set(FORK_FILES)
            or any(not isinstance(v, str) or not SHA64.fullmatch(v)
                   for v in shared.values())):
        blockers.append("missing or invalid exact shared-source file hashes")

    digest = request["common_base_digest"]
    if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
        blockers.append("no immutable pinned common-base digest available")
    persistence = request["image_persistence"]
    if persistence not in PERSISTENCE:
        blockers.append("no durable OCI image persistence plan declared")

    return {
        "schema": "ivanka.px.hosted-build-readiness.v1",
        "tool": tool,
        "adapter_commit": adapter,
        "base_commit": frozen_contract.COMMIT,
        "old_lineage_rejected": adapter in old,
        "shared_source_attested": not any(
            "attestation" in b or "denovo" in b for b in blockers),
        "frozen_seven_intact": registry["policy"]["frozen_seven_manifest_sha256"]
                               == frozen_contract.MANIFEST,
        "image_persistence": persistence,
        "blockers": blockers,
        "prerequisites_met": not blockers,
        # A separate future decision must authorize any actual image build.
        "builds_permitted": False,
        "status": "blocked" if blockers else "source-audit-pass",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("audit",))
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--adapter-repo", required=True)
    parser.add_argument("--adapter-commit", required=True)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--attestation-path", required=True)
    parser.add_argument("--common-base-digest", required=True)
    parser.add_argument("--image-persistence", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = audit(vars(args), args.registry)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("readiness " + report["status"] + ": " + str(len(report["blockers"])) +
          " blocker(s); builds_permitted=false", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
