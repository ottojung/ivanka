#!/usr/bin/env python3
"""Source-only verifier for the PX Unicycler / SAVAGE dependency donors.

Scope: re-derive the SPAdes and CPython 2.7 source pins from immutable
upstream objects, check that the two frozen-baseline MiCall adapter commits
change adapter files only, run a minimal *source-only* adapter build/test
(py_compile + static de-novo CLI contract), and emit a compact evidence JSON.

This script never starts a container, touches a registry or edits the frozen
MiCall baseline.  ``--fetch`` downloads pinned source archives into the cache;
``--online`` re-reads the two upstream tags with git ls-remote.  Without those
flags every check is computed from local, already-attested inputs.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import py_compile
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FROZEN_MASTER = "8458f9e5d34c39a6694b1fb6a40e055d7ce89553"
ADAPTER_PARENT = FROZEN_MASTER
ALLOWED_ADAPTER_PATHS = {
    ".dockerignore",
    "Containerfile.assembler-bench",
    "assembler-bench/README.md",
    "micall/core/benchmark_assembler.py",
    "micall/core/denovo.py",
    "micall/tests/test_benchmark_assembler.py",
    "micall/tests/test_denovo.py",
}

TOOLS = {
    "unicycler": {
        "adapter_branch": "bench/minimal-8458f9e5-unicycler-20261123",
        "adapter_commit": "5ad7874fe193043fa378063efc123018bff546da",
        "adapter_files": {
            "benchmark_assembler.py": "3848b4442b5015057fce79c5cfc8ecc761d1713fb7c59834929e6a147883bdc0",
            "denovo.py": "7294ebb59cd0504d47e179afdf04e4c8bb7c272dbbbdcabdd8ac8b07191b7c39",
        },
        "staged_dir": "unicycler-image",
        "required_strings": ("-1", "-2", "unicycler", "assembly.fasta"),
        "forbidden_strings": ("--ref", "--count_strains"),
    },
    "savage-denovo": {
        "adapter_branch": "bench/frozen-8458f9e5-savage-20261123",
        "adapter_commit": "0919ffa97f609b6f0b650ce834f0fc79822f18e5",
        "adapter_files": {
            "benchmark_assembler.py": "687bdbbe155ffe1243957394fdb889a51223fde80595b682747ffa99a399b919",
            "denovo.py": "7a5be8d7d26f5232b0cebf4a054e5d769afd29a2e7375e9eeb0f5786568ceedb",
        },
        "staged_dir": "savage-image",
        "required_strings": ("-p1", "-p2", "savage", "contigs_stage_c.fasta"),
        "forbidden_strings": ("--ref", "--count_strains"),
    },
}

# Exact upstream source objects.  Hashes are of the byte-for-byte archives,
# never inferred from a tag name or a prebuilt binary.
ARCHIVES = {
    "spades-v3.15.5.tar.gz": {
        "url": "https://github.com/ablab/spades/archive/refs/tags/v3.15.5.tar.gz",
        "sha256": "9848b69a3a6bab4621eb82b71cac6ed96b111c4109c754e283596e9fa3184b1b",
        "bytes": 15310638,
        "role": "spades-core donor source (ablab/spades v3.15.5)",
    },
    "Python-2.7.18.tgz": {
        "url": "https://www.python.org/ftp/python/2.7.18/Python-2.7.18.tgz",
        "sha256": "da3080e3b488f648a3d7a4560ddee895284c3380b11d6de75edb986526b9a814",
        "bytes": 17539408,
        "role": "python2.7 donor source (canonical python.org release)",
    },
    "cpython-v2.7.18.tar.gz": {
        "url": "https://github.com/python/cpython/archive/refs/tags/v2.7.18.tar.gz",
        "sha256": "aa3822dc1615ccaf88352f1c4f2e5687d708be9a45c4c1c93cec64ee123dbec7",
        "bytes": 17517628,
        "role": "python2.7 donor source (cpython tag mirror, cross-check)",
    },
    "scipy-1.2.3.tar.gz": {
        "url": "https://files.pythonhosted.org/packages/62/4f/7e95c5000c411164d5ca6f55ac54cda5d200a3b6719dafd215ee0bd61578/scipy-1.2.3.tar.gz",
        "sha256": "ecbe6413ca90b8e19f8475bfa303ac001e81b04ec600d17fa7f816271f7cca57",
        "bytes": 23335997,
        "role": "last Python-2.7-compatible scipy release (SAVAGE runtime dependency)",
    },
}

UPSTREAM_TAGS = {
    "ablab/spades v3.15.5": ("https://github.com/ablab/spades.git", "refs/tags/v3.15.5", "896694ce5c7a9050a6ffa9fccc950a4cd9f04363"),
    "python/cpython v2.7.18": ("https://github.com/python/cpython.git", "refs/tags/v2.7.18", "41ca0e7833977c2475722ccc3dd5c16865d96dc1"),
}

NATIVE_ASSETS = {
    "unicycler": ("native/unicycler-pinned/cpp_functions.so", "293f840641afaf17ef8b73858ecc7418553c453958bfece305f658223f2dc668"),
    "savage-denovo": ("native/savage-pinned/ViralQuasispecies", "199d97b7330df213f0adf99aaebb8f74d59806dfe90379f15dea28f0aa0c6590"),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(clone: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(clone), *args], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()


def record(checks: list, name: str, ok: bool, detail: str) -> bool:
    checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    return ok


def adapter_contract(name: str, raw: bytes, tool: str, spec: dict) -> dict:
    """Static de-no-only contract; docstrings are not CLI arguments."""
    tree = ast.parse(raw.decode("utf-8"), filename=name)
    docs = {ast.get_docstring(tree)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            docs.add(ast.get_docstring(node))
    constants = {n.value for n in ast.walk(tree)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)} - docs
    forbidden_absent = not any(tok in constants for tok in spec["forbidden_strings"])
    result = {"forbidden_flags_absent_from_cli_constants": forbidden_absent}
    if name == "benchmark_assembler.py":
        result["required_cli_constants"] = all(tok in constants for tok in spec["required_strings"])
        assemble = next((n for n in ast.walk(tree)
                         if isinstance(n, ast.FunctionDef) and n.name == "assemble"), None)
        result["assemble_signature_fixed"] = bool(
            assemble and [a.arg for a in assemble.args.args] == ["first", "second", "seeds"])
        result["seeds_unused_by_subprocess"] = bool(assemble) and not any(
            isinstance(n, ast.Name) and n.id == "seeds" and isinstance(n.ctx, ast.Load)
            for n in ast.walk(assemble))
    else:
        tag = "unicycler" if tool == "unicycler" else "savage"
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "assemble"]
        result["assemble_called_with_paired_reads_only"] = bool(calls) and all(
            [ast.unparse(a) for a in call.args][:2] == ["fastq1", "fastq2"] for call in calls)
        result["deterministic_cache_scope"] = f"denovo[{tag}]" in constants
    return result


def adapter_checks(micall_clone: Path, staged_root: Path, checks: list) -> dict:
    out = {}
    for tool, spec in TOOLS.items():
        pin = spec["adapter_commit"]
        entry = {"adapter_commit": pin, "adapter_branch": spec["adapter_branch"]}
        parent_ok = git(micall_clone, "rev-parse", pin + "^") == ADAPTER_PARENT
        record(checks, f"{tool}:adapter-parent", parent_ok,
               f"parent of {pin} == frozen {ADAPTER_PARENT}")
        changed = git(micall_clone, "diff", "--name-only", ADAPTER_PARENT, pin).splitlines()
        bad = sorted(set(changed) - ALLOWED_ADAPTER_PATHS)
        record(checks, f"{tool}:adapter-only-diff", not bad and bool(changed),
               f"changed={changed}; unexpected={bad}")
        entry["changed_paths"] = changed
        file_report = {}
        sources = {}
        for name, expected in spec["adapter_files"].items():
            raw = subprocess.run(["git", "-C", str(micall_clone), "show", f"{pin}:micall/core/{name}"],
                                 check=True, stdout=subprocess.PIPE).stdout
            on_disk = staged_root / spec["staged_dir"] / name
            actual = digest(raw)
            match = actual == expected and on_disk.is_file() and sha256_file(on_disk) == expected
            record(checks, f"{tool}:adapter-file:{name}", match,
                   f"git-object sha256={actual}; expected={expected}; staged copy byte-identical={on_disk.is_file() and sha256_file(on_disk) == expected}")
            file_report[name] = {"sha256": actual, "bytes": len(raw), "staged_copy_match": match}
            sources[name] = raw
        entry["adapter_files"] = file_report

        # Minimal source-only adapter build/test: compile + static de-novo contract.
        build = {"compiled": {}, "contract": {}}
        with tempfile.TemporaryDirectory(prefix="px-adapter-build-") as tmp:
            for name, raw in sources.items():
                src = Path(tmp) / name
                src.write_bytes(raw)
                pyc = Path(tmp) / (name + "c")
                py_compile.compile(str(src), cfile=str(pyc), doraise=True)
                build["compiled"][name] = {"py_compile": "OK", "pyc_bytes": pyc.stat().st_size}
            for name, raw in sources.items():
                contract = adapter_contract(name, raw, tool, spec)
                ok = all(contract.values())
                record(checks, f"{tool}:adapter-contract:{name}", ok, json.dumps(contract, sort_keys=True))
                build["contract"][name] = contract
        entry["minimal_source_only_build"] = build

        rel, expected_native = NATIVE_ASSETS[tool]
        native = staged_root.parent / rel
        ok = native.is_file() and sha256_file(native) == expected_native
        record(checks, f"{tool}:native-asset", ok,
               f"{native}: sha256={sha256_file(native) if native.is_file() else 'MISSING'}; expected={expected_native}")
        entry["native_asset"] = {"path": str(native), "sha256_expected": expected_native,
                                 "verified": ok}
        out[tool] = entry
    return out


def archive_checks(cache: Path, checks: list, fetch: bool) -> dict:
    out = {}
    cache.mkdir(parents=True, exist_ok=True)
    for name, spec in ARCHIVES.items():
        path = cache / name
        if not path.is_file() and fetch:
            urllib.request.urlretrieve(spec["url"], path)
        ok = path.is_file() and sha256_file(path) == spec["sha256"] and path.stat().st_size == spec["bytes"]
        record(checks, f"archive:{name}", ok,
               f"sha256={sha256_file(path) if path.is_file() else 'MISSING'}; expected={spec['sha256']}; "
               f"bytes={path.stat().st_size if path.is_file() else 0}; expected_bytes={spec['bytes']}")
        out[name] = {"url": spec["url"], "role": spec["role"], "sha256": spec["sha256"],
                     "bytes": spec["bytes"], "verified": ok}
    return out


def online_checks(checks: list) -> dict:
    out = {}
    for label, (repo, ref, expected) in UPSTREAM_TAGS.items():
        result = subprocess.run(["git", "ls-remote", repo, ref], check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()
        actual = result.split()[0] if result else ""
        ok = actual == expected
        record(checks, f"tag:{label}", ok, f"git ls-remote {ref} -> {actual}; expected {expected}")
        out[label] = {"repo": repo, "ref": ref, "commit": actual, "expected": expected, "verified": ok}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--micall-clone", type=Path,
                        default=Path("/workspace/ivanka-exploratory-ten-20261121/micall-adapter-pins-20261125"))
    parser.add_argument("--staged-root", type=Path,
                        default=Path("/workspace/ivanka-exploratory-ten-20261121/native"))
    parser.add_argument("--cache", type=Path,
                        default=Path("/workspace/ivanka-exploratory-ten-20261121/dependency-evidence-cache-20261125"))
    parser.add_argument("--fetch", action="store_true", help="download pinned archives into --cache")
    parser.add_argument("--online", action="store_true", help="re-read upstream tags with git ls-remote")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    checks: list = []
    evidence = {
        "schema": "ivanka.px.dependency-donor-evidence.v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "source-only; no OCI build; no live container; no registry/frozen/cfe-lab mutation",
        "frozen_master": FROZEN_MASTER,
        "adapters": adapter_checks(args.micall_clone, args.staged_root, checks),
        "source_archives": archive_checks(args.cache, checks, args.fetch),
    }
    if args.online:
        evidence["upstream_tags"] = online_checks(checks)
    else:
        evidence["upstream_tags"] = {
            label: {"repo": repo, "ref": ref, "commit": expected,
                    "verified": False, "note": "cached pin; pass --online to re-read"}
            for label, (repo, ref, expected) in UPSTREAM_TAGS.items()
        }
    failures = [c for c in checks if c["status"] != "PASS"]
    evidence["checks"] = checks
    evidence["status"] = "PASS" if not failures else "FAIL"
    evidence["failed_checks"] = [c["check"] for c in failures]
    text = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
