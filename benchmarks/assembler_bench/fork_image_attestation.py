"""Independent fork-commit, image, installed-source and binary audit.

The exact ottojung/MiCall source commit is an executable input contract.
Image labels alone are never sufficient provenance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from benchmarks.expanded.adapters import ASSEMBLERS, PROGRAMS
from .micall_source_guard import (
    fork_commit_url, repo_name, validate_fork_image_manifest,
)

SOURCE_REPO = "https://github.com/ottojung/MiCall"
FORK_FILES = ("denovo.py", "assembler_commands.py",
              "assembler_dispatch.py", "assembler_inputs.py")
HEX64 = re.compile(r"^[a-f0-9]{64}$")
OCI_PROBE = """
import hashlib, importlib, json, shutil
from pathlib import Path
names = ("denovo", "assembler_commands", "assembler_dispatch", "assembler_inputs")
files = {{}}
for name in names:
    module = importlib.import_module("micall.core." + name)
    files[name + ".py"] = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
programs = {{}}
for name in {programs!r}:
    resolved = shutil.which(name)
    if resolved is not None:
        programs[name] = hashlib.sha256(Path(resolved).read_bytes()).hexdigest()
tool = Path("/usr/local/bin/ivanka")
legacy = Path("/opt/micall-iva-compat/samtools")
legacy_sha = hashlib.sha256(legacy.read_bytes()).hexdigest() if legacy.is_file() else None
print(json.dumps({{"files":files,"programs":programs,
    "ivanka_elf":tool.is_file() and tool.open("rb").read(4).hex()=="7f454c46",
    "iva_compatible_samtools_sha256":legacy_sha}}))
"""


def _git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, timeout=30).strip()


def checkout_info(root):
    root = Path(root).resolve()
    if repo_name(_git(root, "remote", "get-url", "origin")) != "ottojung/micall":
        raise ValueError("source checkout is not canonical ottojung/MiCall")
    sha = _git(root, "rev-parse", "HEAD")
    fork_commit_url(sha)
    if _git(root, "status", "--porcelain"):
        raise ValueError("source checkout is dirty or has untracked edits")
    hashes = {}
    for name in FORK_FILES:
        f = root / "micall" / "core" / name
        hashes[name] = hashlib.sha256(f.read_bytes()).hexdigest()
    return {"root": str(root), "commit": sha, "source_hashes": hashes,
            "dockerfile_sha256": hashlib.sha256(
                (root / "Dockerfile.assembler-bench").read_bytes()).hexdigest(),
            "base_dockerfile_sha256": hashlib.sha256(
                (root / "Dockerfile").read_bytes()).hexdigest()}


def inspect(ref):
    output = subprocess.check_output(
        ["podman", "image", "inspect", "--format", "{{json .}}", ref],
        text=True, timeout=60)
    return json.loads(output)


def _id(info):
    value = info.get("Id", "").removeprefix("sha256:")
    if not HEX64.fullmatch(value):
        raise ValueError("image has no immutable full SHA-256 identity")
    return value


def _probe(image, name):
    code = OCI_PROBE.format(programs=tuple(PROGRAMS[name]))
    command = ["podman", "run", "--rm", "--pull=never", "--network=none",
               "--userns=host", "--entrypoint", "/opt/venv/bin/python",
               image, "-c", code]
    result = subprocess.run(command, text=True, capture_output=True,
                            timeout=180, check=True)
    return json.loads(result.stdout)


def verify(images, base_image, fork):
    """Fail closed against spoofed labels, other bases and mutated code."""
    if set(images) != set(ASSEMBLERS):
        raise ValueError("all seven source-built MiCall images are required")
    source = checkout_info(fork)
    commit = source["commit"]
    base = inspect(base_image)
    base_id = _id(base)
    labels = base.get("Config", {}).get("Labels") or {}
    if (labels.get("org.opencontainers.image.source") != SOURCE_REPO
            or labels.get("org.opencontainers.image.revision") != commit):
        raise ValueError("base image was not built at canonical fork commit")
    layers = base.get("RootFS", {}).get("Layers") or []
    if not layers:
        raise ValueError("fork MiCall base lacks immutable layers")
    results = {}
    for name in ASSEMBLERS:
        image = images[name]
        info = inspect(image)
        identifier = _id(info)
        if not HEX64.fullmatch(image) or identifier != image:
            raise ValueError(
                f"{name}: image reference must be the verified immutable ID")
        actual = info.get("Config", {})
        labels = actual.get("Labels") or {}
        if (labels.get("org.opencontainers.image.source") != SOURCE_REPO
                or labels.get("org.opencontainers.image.revision") != commit
                or labels.get("org.ottojung.micall.common-base")
                not in (base_id, "sha256:" + base_id)
                or labels.get("org.ottojung.micall.assembler") != name
                or "MICALL_DENOVO_ASSEMBLER=" + name not in
                (actual.get("Env") or [])):
            raise ValueError(f"{name}: source/assembler binding mismatch")
        image_layers = info.get("RootFS", {}).get("Layers") or []
        if image_layers[:len(layers)] != layers:
            raise ValueError(f"{name}: MiCall downstream base layers differ")
        probe = _probe(identifier, name)
        if probe.get("files") != source["source_hashes"]:
            raise ValueError(f"{name}: installed MiCall source differs from fork")
        if not probe.get("ivanka_elf"):
            raise ValueError(f"{name}: native Ivanka ELF donor not verified")
        if set(probe.get("programs", {})) != set(PROGRAMS[name]):
            raise ValueError(f"{name}: assembler executable missing")
        legacy_sha = probe.get("iva_compatible_samtools_sha256")
        if not isinstance(legacy_sha, str) or not HEX64.fullmatch(legacy_sha):
            raise ValueError(f"{name}: pinned IVA samtools compatibility missing")
        if any(not HEX64.fullmatch(x) for x in probe["programs"].values()):
            raise ValueError(f"{name}: invalid executable digest")
        record = {
            "source_repository": SOURCE_REPO,
            "source_commit": commit, "baseline_commit": commit,
            "source_url": fork_commit_url(commit),
            "baseline_url": fork_commit_url(commit),
            "image_sha256": identifier,
            "dockerfile_sha256": source["dockerfile_sha256"],
            "oci_labels": labels, "independently_verified_build": True,
        }
        validate_fork_image_manifest(record)
        results[name] = {**record, "assembler": name,
                         "binary_sha256": probe["programs"],
                         "source_file_sha256": probe["files"],
                         "ivanka_elf": True,
                         "iva_compatible_samtools_sha256": legacy_sha}
    return {
        "schema": "ivanka.assembler-bench.fork-oci-attestation.v1",
        "source_repository": SOURCE_REPO,
        "source_commit": commit, "source_url": fork_commit_url(commit),
        "base_image_sha256": base_id,
        "base_dockerfile_sha256": source["base_dockerfile_sha256"],
        "candidate_dockerfile_sha256": source["dockerfile_sha256"],
        "source_file_sha256": source["source_hashes"], "images": results,
        "status": "VERIFIED_BY_INSTALLED_SOURCE_AND_BINARY_SHA",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fork-checkout", required=True, type=Path)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = verify(json.loads(args.images.read_text()),
                    args.base_image, args.fork_checkout)
    with args.output.open("x") as out:
        json.dump(report, out, sort_keys=True, indent=2)
        out.write("\n")
    print("FORK_MiCall_IMAGE_SOURCE_AND_BINARY_VERIFIED",
          report["source_commit"], len(report["images"]))


if __name__ == "__main__":
    main()
