"""Independent audit of seven distinct branch-built, tool-only MiCall images."""
import argparse
import json
from pathlib import Path

from benchmarks.expanded.adapters import ASSEMBLERS, PROGRAMS
from .fork_image_attestation import (
    HEX64, SOURCE_REPO, OCI_PROBE, checkout_info, inspect, _id, _git)
from .micall_source_guard import fork_commit_url

SCHEMA = "ivanka.assembler-bench.dedicated-fork-images.v1"


def _source(name, root, baseline):
    root = Path(root)
    source = checkout_info(root)
    branch = "bench/assembler-" + name
    if _git(root, "symbolic-ref", "--short", "HEAD") != branch:
        raise ValueError(f"{name}: wrong source branch")
    if (root/"assembler-bench/selected").read_text().strip() != name:
        raise ValueError(f"{name}: wrong committed assembler profile")
    if (root/"assembler-bench/baseline-commit").read_text().strip() != baseline:
        raise ValueError(f"{name}: wrong MiCall downstream baseline")
    if (_git(root, "rev-parse", "HEAD:micall") !=
            _git(root, "rev-parse", baseline+":micall")):
        raise ValueError(f"{name}: downstream MiCall code differs")
    published = _git(root, "ls-remote", "--heads", "origin",
                     "refs/heads/"+branch).split()
    if not published or published[0] != source["commit"]:
        raise ValueError(f"{name}: source branch has not been published")
    dockerfile = (root/"Dockerfile.assembler-bench").read_text()
    if (f'org.ottojung.micall.assembler="{name}"' not in dockerfile
            or f'ENV MICALL_DENOVO_ASSEMBLER={name}' not in dockerfile):
        raise ValueError(f"{name}: wrong dedicated Dockerfile assembler")
    for other in ASSEMBLERS:
        if other == name:
            continue
        if f'ENV MICALL_DENOVO_ASSEMBLER={other}' in dockerfile.splitlines():
            raise ValueError(f"{name}: mixed assembler configuration")
    return source


def _program_probe(image, names):
    """No network and no read inputs: hash the actual installed commands."""
    import subprocess
    code = OCI_PROBE.format(programs=tuple(names))
    result = subprocess.run(
        ["podman", "run", "--rm", "--pull=never", "--network=none",
         "--userns=host", "--entrypoint", "/opt/venv/bin/python",
         image, "-c", code],
        capture_output=True, text=True, timeout=180, check=True)
    return json.loads(result.stdout)


def verify(images, roots, base_image):
    """Refuse mixed branches, duplicate images, extra tools and source changes."""
    if set(images) != set(ASSEMBLERS) or set(roots) != set(ASSEMBLERS):
        raise ValueError("requires exactly seven pinned images and source branches")
    if any(not HEX64.fullmatch(x) for x in images.values()):
        raise ValueError("candidate image reference must be a full immutable ID")
    if len(set(images.values())) != len(ASSEMBLERS):
        raise ValueError("two assemblers reused the same image identity")
    if not HEX64.fullmatch(base_image):
        raise ValueError("common base must be identified by immutable image ID")
    base = inspect(base_image)
    base_id = _id(base)
    if base_id != base_image:
        raise ValueError("common base ID does not match inspected contents")
    base_labels = (base.get("Config") or {}).get("Labels") or {}
    baseline = base_labels.get("org.opencontainers.image.revision", "")
    fork_commit_url(baseline)
    if base_labels.get("org.opencontainers.image.source") != SOURCE_REPO:
        raise ValueError("base is not from the canonical MiCall fork")
    layers = (base.get("RootFS") or {}).get("Layers") or []
    if not layers:
        raise ValueError("common base missing immutable OCI layers")
    all_programs = sorted({program for values in PROGRAMS.values()
                           for program in values})
    common = _program_probe(base_id, all_programs)
    common_programs = set(common["programs"])
    if common_programs != set(PROGRAMS["iva"]):
        raise ValueError("common baseline already contains extra assemblers")
    results = {}
    seen_commits = set()
    for name in ASSEMBLERS:
        src = _source(name, roots[name], baseline)
        if src["commit"] in seen_commits:
            raise ValueError(f"{name}: two assembler branches share one commit")
        seen_commits.add(src["commit"])
        if src["source_hashes"] != common["files"]:
            raise ValueError(f"{name}: MiCall branch differs from common source")
        image_id = images[name]
        image = inspect(image_id)
        if _id(image) != image_id:
            raise ValueError(f"{name}: image identity differs")
        cfg = image.get("Config") or {}
        labels = cfg.get("Labels") or {}
        required = {
            "org.opencontainers.image.source": SOURCE_REPO,
            "org.opencontainers.image.revision": src["commit"],
            "org.ottojung.micall.source-branch": "bench/assembler-"+name,
            "org.ottojung.micall.assembler": name,
            "org.ottojung.micall.common-base": base_id,
            "org.ottojung.micall.common-baseline-commit": baseline,
        }
        if any(labels.get(k) != v for k,v in required.items()):
            raise ValueError(f"{name}: source/branch/base image labels mismatch")
        if ("MICALL_DENOVO_ASSEMBLER="+name not in (cfg.get("Env") or []) or
                sum(x.startswith("MICALL_DENOVO_ASSEMBLER=")
                    for x in (cfg.get("Env") or [])) != 1):
            raise ValueError(f"{name}: runtime assembler choice not frozen")
        img_layers = (image.get("RootFS") or {}).get("Layers") or []
        if img_layers[:len(layers)] != layers:
            raise ValueError(f"{name}: common MiCall base layers differ")
        probe = _program_probe(image_id, all_programs)
        if probe["files"] != common["files"]:
            raise ValueError(f"{name}: installed MiCall source not fork-equivalent")
        expected = common_programs | set(PROGRAMS[name])
        if set(probe["programs"]) != expected:
            raise ValueError(f"{name}: missing or extraneous assembler executables")
        if bool(probe["ivanka_elf"]) != (name=="ivanka"):
            raise ValueError(f"{name}: unexpected or missing native Ivanka ELF")
        if any(not HEX64.fullmatch(h) for h in probe["programs"].values()):
            raise ValueError(f"{name}: invalid executable SHA")
        results[name] = {
            "source_repository":SOURCE_REPO,
            "source_branch":"bench/assembler-"+name,
            "source_commit":src["commit"],
            "source_url":fork_commit_url(src["commit"]),
            "baseline_commit":baseline,
            "baseline_url":fork_commit_url(baseline),
            "image_sha256":image_id,
            "dockerfile_sha256":src["dockerfile_sha256"],
            "installed_modules_sha256":probe["files"],
            "executables_sha256":probe["programs"],
            "selected_assembler":name,
        }
    return {"schema":SCHEMA,
            "status":"SEVEN_INDEPENDENT_BRANCH_IMAGES_VERIFIED",
            "source_repository":SOURCE_REPO,
            "base_image_sha256":base_id,
            "baseline_commit":baseline,
            "baseline_url":fork_commit_url(baseline),
            "installed_modules_sha256":common["files"],
            "images":results}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--images",type=Path,required=True)
    ap.add_argument("--source-roots",type=Path,required=True)
    ap.add_argument("--base-image",required=True)
    ap.add_argument("--output",type=Path,required=True)
    args = ap.parse_args()
    report = verify(json.loads(args.images.read_text()),
                    json.loads(args.source_roots.read_text()),
                    args.base_image)
    with args.output.open("x") as out:
        json.dump(report,out,indent=2,sort_keys=True)
        out.write("\n")
    print(report["status"],len(report["images"]),report["baseline_commit"])


if __name__=="__main__":
    main()
