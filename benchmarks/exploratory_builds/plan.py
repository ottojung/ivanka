"""Bind pinned adapter branches into one regenerable, nonqualifying build plan.

The authoritative image recipe remains the tool-only Dockerfile committed on
each MiCall adapter branch. This module only records the exact inputs and the
launcher command that must build that recipe; it never performs an OCI build.
"""
import hashlib
import json
import re
from pathlib import Path

from assembler_bench.exploratory_policy import EXPERIMENTAL, ORIGINAL, checked

HERE = Path(__file__).resolve().parent
BENCHMARKS = HERE.parent
REGISTRY = BENCHMARKS / "assembler_bench" / "exploratory_candidates.json"
PLANS = HERE / "build_plans.json"
AUDIT = HERE / "recipe_audit.json"

SCHEMA = "ivanka.exploratory.build-plan.v1"
LAUNCHER = "assembler_bench.exploratory_runtime.cli"
RECIPE = "Dockerfile.assembler-bench"
# Unicycler's frozen comparison lineage is a different tool-donor lineage:
# its immutable recipe is Containerfile.assembler-bench on clinical MiCall
# master 8458f9e5, not the eeca0381 Dockerfile.assembler-bench branch.
RECIPES = {"unicycler": "Containerfile.assembler-bench"}
BASELINES = {"unicycler": "8458f9e5d34c39a6694b1fb6a40e055d7ce89553"}
FROZEN_LINEAGE = HERE / "frozen_unicycler_lineage.json"
BASELINE = "/workspace/ivanka-exploratory-ten-20261121/budget-baseline.json"
REGISTRY_ARG = "benchmarks/assembler_bench/exploratory_candidates.json"
FROZEN_MANIFEST = "9db6e1b569b17aed8b7e96abea495b09374e609478834371e2943b16df36884f"
RESERVE_BYTES = 1024**3

# SAVAGE's adapter branch drops the '-denovo' registry suffix: it is the one
# de-novo-only adapter, so the branch name is pinned explicitly rather than
# derived from the candidate id.
ADAPTER_BRANCHES = {
    "skesa": "bench/assembler-skesa",
    "idba-ud": "bench/assembler-idba-ud",
    "minia": "bench/assembler-minia",
    "ray": "bench/assembler-ray",
    "unicycler": "bench/minimal-8458f9e5-unicycler-20261123",
    "tadpole": "bench/assembler-tadpole",
    "soapdenovo2": "bench/assembler-soapdenovo2",
    "fermi-lite": "bench/assembler-fermi-lite",
    "penguin": "bench/assembler-penguin",
    "savage-denovo": "bench/assembler-savage",
}

POLICY_KEYS = (
    "min_workspace_free_bytes",
    "max_concurrent_exploratory_workers",
    "max_container_wall_seconds",
    "max_sampled_process_tree_rss_bytes",
    "dedicated_image_store_root",
    "dedicated_podman_storage_conf",
    "frozen_seven_manifest_sha256",
    "qualification_admission",
)

SHA64 = re.compile(r"[a-f0-9]{64}\Z")
DIGEST = re.compile(r"sha256:[a-f0-9]{64}\Z")
PLACEHOLDER = re.compile(r"\{([A-Z0-9_]+)\}")
FORBIDDEN = re.compile(
    r"(?i)(?:\bhxb2\b|reference[_-]?(?:panel|genome|fasta|catalog|truth)"
    r"|benchmark[_-]?panel|alignment[_-]?score|iva[_-]?score"
    r"|--(?:reference|ref|panel)(?:\b|=))"
)


def _read(registry_path):
    data = checked(registry_path)
    return data, Path(registry_path).read_bytes()


def _audit():
    document = json.loads(AUDIT.read_text())
    if (document.get("schema") != "ivanka.exploratory.recipe-audit.v1"
            or set(document["recipes"]) != EXPERIMENTAL):
        raise ValueError("recipe audit drifted from the explorer roster")
    return document["recipes"]


def _command(tool, adapter_commit, baseline, repo, source_commit, image_tag,
             recipe_name, audit):
    """Exact launcher argv; unresolved fields require an admitted build."""
    arg = "--build-arg"
    pairs = sorted(audit["extra_build_args"].items())
    pairs.extend((name, "{" + name + "}")
                 for name in sorted(audit["extra_placeholders"]))
    if tool == "unicycler":
        pairs = [
            ("BENCHMARK_ASSEMBLER_SHA256", audit["adapter_commands_sha256"]),
            ("BENCHMARK_TEST_SHA256", audit["adapter_dispatch_sha256"]),
            *pairs,
        ]
        first = [
            arg, "ASSEMBLER_TOOL_IMAGE={ASSEMBLER_TOOL_IMAGE}",
            arg, "MICALL_BASE_COMMIT=" + baseline,
            arg, "MICALL_SOURCE_COMMIT=" + adapter_commit,
            arg, "TOOL_IMAGE_ID={TOOL_IMAGE_ID}",
        ]
    else:
        pairs = [
            ("MICALL_ADAPTER_COMMANDS_SHA256", audit["adapter_commands_sha256"]),
            ("MICALL_ADAPTER_DISPATCH_SHA256", audit["adapter_dispatch_sha256"]),
            *pairs,
        ]
        first = [
            arg, "FORK_BASE_IMAGE={BASE_IMAGE_DIGEST}",
            arg, "MICALL_FORK_SOURCE_COMMIT=" + adapter_commit,
            arg, "MICALL_FORK_BASE_COMMIT=" + baseline,
            arg, "TOOL_SOURCE_REPO=" + repo,
            arg, "TOOL_SOURCE_COMMIT=" + source_commit,
            arg, "TOOL_BINARY_SHA256={TOOL_BINARY_SHA256}",
        ]
    extra = [token for name, value in pairs for token in (arg, name + "=" + value)]
    return [
        "python", "-m", LAUNCHER,
        "--registry", "{REGISTRY_PATH}",
        "--baseline", BASELINE,
        "--tool", tool,
        "--mode", "build",
        "--reserve-bytes", str(RESERVE_BYTES),
        "--",
        "podman", "build", "--pull=never",
        "--file", "{ADAPTER_CHECKOUT}/" + recipe_name,
        "--tag", image_tag,
        *first,
        *extra,
        "{ADAPTER_CHECKOUT}",
    ]


def generate(registry_path=REGISTRY):
    """Derive the full build plan from the fail-closed source registry."""
    data, blob = _read(registry_path)
    policy = {key: data["policy"][key] for key in POLICY_KEYS}
    pinning = data["source_pinning"]
    policy["oci_builds_performed"] = pinning["runtime_images_built"]
    policy["pilots_executed"] = pinning["pilots_executed"]
    recipes = _audit()
    builds = []
    for item in sorted(data["candidates"], key=lambda row: row["id"]):
        tool = item["id"]
        adapter = data["adapter_branch_commits"][tool]
        recipe = recipes[tool]
        recipe_name = RECIPES.get(tool, RECIPE)
        baseline = BASELINES.get(tool, data["adapter_baseline_commit"])
        image_tag = "localhost/ivanka-exploratory-%s:%s" % (tool, adapter[:12])
        placeholders = ["ADAPTER_CHECKOUT", "REGISTRY_PATH"]
        placeholders.extend(("ASSEMBLER_TOOL_IMAGE", "TOOL_IMAGE_ID")
                            if tool == "unicycler" else
                            ("BASE_IMAGE_DIGEST", "TOOL_BINARY_SHA256"))
        placeholders.extend(recipe["extra_placeholders"])
        builds.append({
            "id": tool,
            "name": item["name"],
            "image_tag": image_tag,
            "adapter_branch": ADAPTER_BRANCHES[tool],
            "adapter_commit": adapter,
            "common_baseline_commit": baseline,
            "tool_source_repo": item["source_repo"],
            "tool_source_commit": item["source_commit"],
            "tool_license": item.get("source_license"),
            "recipe": recipe_name,
            "recipe_args": {
                **({"BENCHMARK_ASSEMBLER_SHA256":
                    recipe["adapter_commands_sha256"],
                    "BENCHMARK_TEST_SHA256":
                    recipe["adapter_dispatch_sha256"]}
                   if tool == "unicycler" else
                   {"MICALL_ADAPTER_COMMANDS_SHA256":
                    recipe["adapter_commands_sha256"],
                    "MICALL_ADAPTER_DISPATCH_SHA256":
                    recipe["adapter_dispatch_sha256"]}),
                **recipe["extra_build_args"],
            },
            "extra_placeholders": sorted(recipe["extra_placeholders"]),
            "attested_binary_sha256": recipe["attested_binary_sha256"],
            "attestation_provenance": recipe["attestation_provenance"],
            "blockers": recipe["blockers"],
            "build_ready": False,
            "base_image_digest": None,
            "tool_binary_sha256": None,
            "command_template": _command(
                tool, adapter, baseline, item["source_repo"],
                item["source_commit"], image_tag, recipe_name, recipe),
            "required_placeholders": sorted(placeholders),
            # A build plan is a template for a future admitted build; its
            # status is independent of the registry row's current state.
            "status": "source-pinned",
            "qualifying": False,
            "nonqualifying": True,
            "reference_blind": True,
        })
    plan = {
        "schema": SCHEMA,
        "source_registry_sha256": hashlib.sha256(blob).hexdigest(),
        "policy": policy,
        "builds": builds,
    }
    validate(plan, registry_path)
    return plan


def dumps(plan):
    """Canonical serialization so regeneration is byte-for-byte identical."""
    return json.dumps(plan, indent=2, sort_keys=True) + "\n"


def validate_document(path=PLANS, registry_path=REGISTRY):
    """Load a committed plan and validate it against the live fail-closed registry."""
    document = json.loads(Path(path).read_text())
    validate(document, registry_path)
    return document


def validate(plan, registry_path=REGISTRY):
    """Reject any plan that could widen qualification or leak a reference."""
    data, blob = _read(registry_path)
    if (plan.get("schema") != SCHEMA
            or plan.get("source_registry_sha256") != hashlib.sha256(blob).hexdigest()):
        raise ValueError("plan schema or source registry binding drifted")
    policy = plan.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("missing build policy")
    expected = {key: data["policy"][key] for key in POLICY_KEYS}
    expected.update(oci_builds_performed=0, pilots_executed=0)
    if policy != expected:
        raise ValueError("build policy or nonclaim counters drifted")
    if policy["frozen_seven_manifest_sha256"] != FROZEN_MANIFEST:
        raise ValueError("frozen seven manifest must remain untouched")
    if set(data["baseline_assemblers"]) != ORIGINAL:
        raise ValueError("original qualifying roster changed")
    found = FORBIDDEN.search(dumps(plan))
    if found:
        raise ValueError("build plan exposes reference material: " + found.group())

    builds = plan.get("builds")
    if (not isinstance(builds, list) or len(builds) != 10
            or {row.get("id") for row in builds} != EXPERIMENTAL
            or len({row.get("id") for row in builds}) != 10
            or [row["id"] for row in builds] != sorted(EXPERIMENTAL)):
        raise ValueError("build plan must contain exactly ten sorted explorers")
    by_id = {row["id"]: row for row in data["candidates"]}
    recipes = _audit()
    for row in builds:
        _validate_build(row, by_id[row["id"]], data, recipes[row["id"]])


def _validate_build(row, candidate, data, recipe):
    tool = row["id"]
    adapter = data["adapter_branch_commits"][tool]
    expected_tag = "localhost/ivanka-exploratory-%s:%s" % (tool, adapter[:12])
    if (row.get("name") != candidate["name"]
            or row.get("image_tag") != expected_tag
            or row.get("adapter_branch") != ADAPTER_BRANCHES[tool]
            or row.get("adapter_commit") != adapter
            or row.get("common_baseline_commit")
            != BASELINES.get(tool, data["adapter_baseline_commit"])
            or row.get("tool_source_repo") != candidate["source_repo"]
            or row.get("tool_source_commit") != candidate["source_commit"]
            or row.get("tool_license") != candidate.get("source_license")
            or row.get("recipe") != RECIPES.get(tool, RECIPE)):
        raise ValueError("pinned build inputs drifted: " + tool)
    if (row.get("base_image_digest") is not None
            or row.get("tool_binary_sha256") is not None):
        raise ValueError("no binary or image digest may be invented: " + tool)
    if tool == "unicycler":
        expected_args = {
            "BENCHMARK_ASSEMBLER_SHA256": recipe["adapter_commands_sha256"],
            "BENCHMARK_TEST_SHA256": recipe["adapter_dispatch_sha256"],
            **recipe["extra_build_args"],
        }
    else:
        expected_args = {
            "MICALL_ADAPTER_COMMANDS_SHA256": recipe["adapter_commands_sha256"],
            "MICALL_ADAPTER_DISPATCH_SHA256": recipe["adapter_dispatch_sha256"],
            **recipe["extra_build_args"],
        }
    if (row.get("recipe_args") != expected_args
            or row.get("extra_placeholders") != sorted(recipe["extra_placeholders"])
            or row.get("attested_binary_sha256") != recipe["attested_binary_sha256"]
            or row.get("blockers") != recipe["blockers"]
            or row.get("build_ready") is not False):
        raise ValueError("pinned recipe args or blockers drifted: " + tool)
    if (row.get("status") != "source-pinned"
            or row.get("qualifying") is not False
            or row.get("nonqualifying") is not True
            or row.get("reference_blind") is not True):
        raise ValueError("explorer must stay source-pinned and nonqualifying: " + tool)

    command = row.get("command_template")
    if not isinstance(command, list) or not command:
        raise ValueError("missing build command: " + tool)
    baseline = BASELINES.get(tool, data["adapter_baseline_commit"])
    joined = " ".join(command)
    if (command[:4] != ["python", "-m", LAUNCHER, "--registry"]
            or "--mode" not in command or "build" not in command
            or "podman" not in command or "--detach" in command
            or BASELINE not in command or baseline not in joined
            or "{REGISTRY_PATH}" not in command
            or "{ADAPTER_CHECKOUT}/" + RECIPES.get(tool, RECIPE) not in command):
        raise ValueError("build must run the one-worker launcher, detached builds banned: " + tool)
    if "--reserve-bytes" not in command:
        raise ValueError("launcher reservation missing: " + tool)
    position = command.index("--reserve-bytes") + 1
    if (position >= len(command) or not command[position].isdigit()
            or not RESERVE_BYTES <= int(command[position]) <= 4 * RESERVE_BYTES):
        raise ValueError("launcher reservation must stay within 1-4 GiB: " + tool)
    if tool == "unicycler":
        if adapter not in joined or "MICALL_BASE_COMMIT=" + baseline not in joined:
            raise ValueError("frozen lineage pins missing from build command: " + tool)
        if "FORK_BASE_IMAGE" in joined or "MICALL_FORK_SOURCE_COMMIT" in joined:
            raise ValueError("stale clinical donor lineage in build command: " + tool)
    elif adapter not in joined or candidate["source_commit"] not in joined:
        raise ValueError("launcher command lost its source pins: " + tool)
    for name, value in expected_args.items():
        if name + "=" + value not in command:
            raise ValueError("audited build arg missing: " + tool + " " + name)
    for name in recipe["extra_placeholders"]:
        if name + "={" + name + "}" not in command:
            raise ValueError("required attested build arg missing: " + tool + " " + name)
    placeholders = set()
    for token in command:
        placeholders.update(PLACEHOLDER.findall(token))
    if placeholders != set(row.get("required_placeholders", [])):
        raise ValueError("unexpected command placeholders: " + tool)


def render(plan, tool, base_image_digest, tool_binary_sha256, adapter_checkout,
           registry_path, extra_values=None):
    """Materialize an admitted build command; never executes it."""
    if not adapter_checkout or not Path(adapter_checkout).is_absolute():
        raise ValueError("adapter checkout must be an absolute path")
    if (not registry_path
            or not Path(registry_path).is_absolute()
            or not Path(registry_path).name == Path(REGISTRY_ARG).name):
        raise ValueError("registry path must be absolute and name the source registry")
    row = next((item for item in plan["builds"] if item["id"] == tool), None)
    if row is None:
        raise ValueError("unknown explorer: " + tool)
    if tool == "unicycler":
        supplied = extra_values or {}
        values = {
            "ASSEMBLER_TOOL_IMAGE": supplied.get("ASSEMBLER_TOOL_IMAGE"),
            "TOOL_IMAGE_ID": supplied.get("TOOL_IMAGE_ID"),
            "ADAPTER_CHECKOUT": adapter_checkout,
            "REGISTRY_PATH": registry_path,
        }
        if not DIGEST.fullmatch(values["ASSEMBLER_TOOL_IMAGE"] or ""):
            raise ValueError("native tool donor image must be an immutable digest")
        if not SHA64.fullmatch(values["TOOL_IMAGE_ID"] or ""):
            raise ValueError("a real 64-hex native tool image ID is required")
    else:
        if not DIGEST.fullmatch(base_image_digest or ""):
            raise ValueError("base image must be an immutable sha256 digest")
        if not SHA64.fullmatch(tool_binary_sha256 or ""):
            raise ValueError("a real 64-hex tool binary digest is required")
        values = {
            "BASE_IMAGE_DIGEST": base_image_digest,
            "TOOL_BINARY_SHA256": tool_binary_sha256,
            "ADAPTER_CHECKOUT": adapter_checkout,
            "REGISTRY_PATH": registry_path,
        }
        values.update(extra_values or {})
    if set(values) != set(row["required_placeholders"]):
        raise ValueError("missing or unexpected attested build values: " + tool)
    command = []
    for token in row["command_template"]:
        for name, value in values.items():
            token = token.replace("{" + name + "}", value)
        if "{" in token or "}" in token:
            raise ValueError("unresolved build placeholder: " + token)
        command.append(token)
    return command
