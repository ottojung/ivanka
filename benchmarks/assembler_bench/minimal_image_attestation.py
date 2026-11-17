"""External verification of minimally adapted, independently built MiCall images.

No verifier or test code is installed in the benchmark runtime images.
"""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess

from benchmarks.expanded.adapters import ASSEMBLERS

SCHEMA = "ivanka.assembler-bench.minimal-fork-images.v1"
REPO = "https://github.com/ottojung/MiCall"
HEX = re.compile(r"^[a-f0-9]{40}$")
SHA = re.compile(r"^[a-f0-9]{64}$")
ALLOWED = frozenset({
    ".dockerignore", "Containerfile.assembler-bench",
    "assembler-bench/README.md", "micall/core/denovo.py",
    "micall/core/benchmark_assembler.py",
    "micall/tests/test_benchmark_assembler.py",
    "micall/tests/test_denovo.py",
})
TOOLS = {
    "iva": "iva", "ivanka": "ivanka", "abyss": "abyss-pe",
    "haploflow": "haploflow", "megahit": "megahit",
    "spades": "spades.py", "velvet": "velveth",
}

def call(argv, *, timeout=120):
    return subprocess.run(argv, text=True, check=True, capture_output=True,
                          timeout=timeout).stdout.strip()

def git(root, *args):
    return call(["git", "-C", str(root), *args], timeout=30)

def verify_seed_contract(source):
    """Only the normal same-sample G2P optional seed input may reach Rust."""
    tree=ast.parse(source)
    functions={node.name:node for node in tree.body
               if isinstance(node,ast.FunctionDef)}
    if not {"assemble","sample_seeds"} <= set(functions):
        raise ValueError("Ivanka seed adapter lacks the reviewed functions")
    body=functions["assemble"]
    assigned=[node.value for node in ast.walk(body) if isinstance(node,ast.Assign)
              and any(isinstance(target,ast.Name) and target.id=="argv"
                      for target in node.targets)]
    if len(assigned)!=1 or not isinstance(assigned[0],ast.List):
        raise ValueError("Ivanka command is not a fixed list")
    parts=assigned[0].elts
    if (len(parts)!=7 or
            [part.value for part in parts if isinstance(part,ast.Constant)]!=
            ["/usr/local/bin/ivanka","--reads1","--reads2","--output"]):
        raise ValueError("Ivanka received an unexpected command option")
    extensions=[node for node in ast.walk(body) if isinstance(node,ast.Call)
                and isinstance(node.func,ast.Attribute)
                and isinstance(node.func.value,ast.Name)
                and node.func.value.id=="argv" and
                node.func.attr in ("append","extend","insert")]
    if (len(extensions)!=1 or extensions[0].func.attr!="extend"
            or len(extensions[0].args)!=1
            or not isinstance(extensions[0].args[0],ast.List)
            or len(extensions[0].args[0].elts)!=2
            or not isinstance(extensions[0].args[0].elts[0],ast.Constant)
            or extensions[0].args[0].elts[0].value!="--seeds"):
        raise ValueError("unreviewed Ivanka command mutation")
    seed_path=extensions[0].args[0].elts[1]
    if (not isinstance(seed_path,ast.Call)
            or not isinstance(seed_path.func,ast.Name)
            or seed_path.func.id!="str" or len(seed_path.args)!=1
            or not isinstance(seed_path.args[0],ast.BinOp)
            or not isinstance(seed_path.args[0].left,ast.Name)
            or seed_path.args[0].left.id!="work"
            or not isinstance(seed_path.args[0].op,ast.Div)
            or not isinstance(seed_path.args[0].right,ast.Constant)
            or seed_path.args[0].right.value!="seeds.fasta"):
        raise ValueError("Ivanka seeds must use the generated same-sample FASTA")
    calls=[node for node in ast.walk(body) if isinstance(node,ast.Call)
           and isinstance(node.func,ast.Attribute)
           and isinstance(node.func.value,ast.Name)
           and node.func.value.id=="subprocess" and node.func.attr=="run"]
    if (len(calls)!=1 or not any(
            kw.arg=="env" and isinstance(kw.value,ast.Dict)
            and not kw.value.keys for kw in calls[0].keywords)):
        raise ValueError("Ivanka must launch once with empty child environment")
    conditional=[node for node in ast.walk(body) if isinstance(node,ast.If)
                 and extensions[0] in list(ast.walk(node))]
    if (len(conditional)!=1 or
            "sample_seeds" not in ast.unparse(conditional[0].test)):
        raise ValueError("Ivanka seeds must be conditional on same-sample G2P")
    return True


def source(name, root, baseline):
    root = Path(root).resolve(strict=True)
    if git(root, "status", "--porcelain"):
        raise ValueError(f"{name}: dirty source branch")
    revision = git(root, "rev-parse", "HEAD")
    branch = git(root, "branch", "--show-current")
    if not HEX.fullmatch(revision) or not branch.startswith("bench/"):
        raise ValueError(f"{name}: source must be a committed benchmark branch")
    if name not in branch.split("-") or git(root, "merge-base", baseline, revision) != baseline:
        raise ValueError(f"{name}: wrong assembler branch or common source base")
    remote = git(root, "ls-remote", "origin", f"refs/heads/{branch}").split()
    if not remote or remote[0] != revision:
        raise ValueError(f"{name}: source branch not published at its exact commit")
    changed = set(git(root, "diff", "--name-only", baseline, revision).splitlines())
    if not changed <= ALLOWED:
        raise ValueError(f"{name}: changed nonassembler MiCall files: {sorted(changed - ALLOWED)}")
    recipe = (root / "Containerfile.assembler-bench").read_text()
    if ("RUN /opt/venv/bin/python -c" in recipe
            or "HEALTHCHECK" in recipe.upper()
            or "COPY benchmarks/" in recipe
            or "RUN pytest" in recipe
            or "RUN python -m unittest" in recipe):
        raise ValueError(f"{name}: verifier/test included in runtime image recipe")
    operations=[line.strip() for line in recipe.splitlines()
                if line.lstrip().startswith("RUN ")]
    expected=("RUN rm -rf /opt/micall",
              "RUN /opt/uv-home/.local/bin/uv sync",
              "RUN /opt/venv/bin/micall make_blast_db")
    if len(operations)!=3 or any(not op.startswith(need)
                                 for op,need in zip(operations,expected)):
        raise ValueError(f"{name}: unreviewed build-time operation")
    if "micall/tests" not in (root / ".dockerignore").read_text().splitlines():
        raise ValueError(f"{name}: source test suite is copied into runtime image")
    if name=="ivanka":
        verify_seed_contract((root/"micall/core/benchmark_assembler.py").read_text())
    return {"source_branch": branch, "source_commit": revision,
            "source_url": f"{REPO}/tree/{revision}", "changed_files": sorted(changed)}

# This code is supplied by the EXTERNAL preflight to a disposable probe process.
# It is never copied into an image, and it does not run during benchmark timing.
PROBE = r"""
from pathlib import Path
import hashlib, json, shutil
p=Path('/source/micall')
q=Path('/opt/venv/lib/python3.12/site-packages/micall')
assert p.is_dir() and q.is_dir()
assert not Path('/opt/micall/micall/tests').exists()
assert not (q/'tests').exists()
digest=lambda file:hashlib.sha256(file.read_bytes()).hexdigest()
count=0
for f in p.rglob('*'):
    if not f.is_file() or 'tests' in f.relative_to(p).parts:
        continue
    if f.suffix not in ('.py','.json','.fasta','.fa','.csv','.tsv','.yaml','.yml','.txt','.xml','.dat'):
        continue
    target=q/f.relative_to(p)
    assert target.is_file() and digest(f)==digest(target), str(f)
    count+=1
assert count>=150,count
assert digest(Path('/source/uv.lock'))==digest(Path('/opt/micall/uv.lock'))
assert digest(Path('/source/pyproject.toml'))==digest(Path('/opt/micall/pyproject.toml'))
program=shutil.which('PROGRAM_NAME')
assert program, 'assembler program not installed'
contestants=('iva','ivanka','haploflow','megahit','abyss-pe','spades.py','velveth')
installed={name for name in contestants if shutil.which(name)}
assert installed=={'iva','PROGRAM_NAME'},('extra or missing tool',installed)
if 'PROGRAM_NAME'=='ivanka':
    assert Path(program).read_bytes()[:4]==b'\x7fELF'
print(json.dumps({'installed_source_files':count,
                  'assembler_binary':program,
                  'assembler_sha256':digest(Path(program))}))
"""

def image(name, root, image_id, baseline):
    if not SHA.fullmatch(image_id):
        raise ValueError(f"{name}: image must be an immutable 64-digit SHA256 ID")
    inspected=json.loads(call(["podman", "image", "inspect", image_id]))[0]
    labels=inspected.get("Labels") or inspected.get("Config",{}).get("Labels") or {}
    if (inspected.get("Id", "").removeprefix("sha256:") != image_id or
            labels.get("org.opencontainers.image.source") != REPO or
            labels.get("org.opencontainers.image.revision") != git(root, "rev-parse", "HEAD") or
            labels.get("org.ottojung.micall.assembler") != name or
            labels.get("org.ottojung.micall.frozen-upstream-master") != baseline):
        raise ValueError(f"{name}: installed OCI source identity mismatch")
    raw=call(["podman", "run", "--rm", "--pull=never", "--network=none",
              "-v", f"{Path(root).resolve()}:/source:ro",
              "--entrypoint", "/opt/venv/bin/python", image_id,
              "-c", PROBE.replace("PROGRAM_NAME", TOOLS[name])], timeout=180)
    return json.loads(raw.splitlines()[-1])

def verify(images, roots, baseline):
    if not HEX.fullmatch(baseline):
        raise ValueError("common MiCall source commit must be 40 hex digits")
    if set(images) != set(ASSEMBLERS) or set(roots) != set(ASSEMBLERS):
        raise ValueError("exactly seven images and seven distinct source roots required")
    if len(set(images.values())) != 7 or len(set(map(str, roots.values()))) != 7:
        raise ValueError("duplicate source or image identity")
    records={}
    for name in ASSEMBLERS:
        branch=source(name, roots[name], baseline)
        installed=image(name, roots[name], images[name], baseline)
        records[name]={**branch, **installed, "image_sha256":images[name],
                       "baseline_commit":baseline}
    return {"schema":SCHEMA, "status":"EXTERNALLY_ATTESTED_NOT_BENCHMARK_QUALIFIED",
            "source_repository":REPO, "baseline_commit":baseline,
            "images":records}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ("images","source-roots","base","output"):
        parser.add_argument("--"+flag,required=True)
    args=parser.parse_args()
    result=verify(json.loads(Path(args.images).read_text()),
                  json.loads(Path(args.source_roots).read_text()),args.base)
    output=Path(args.output)
    with output.open("x") as target:
        json.dump(result,target,sort_keys=True,indent=2)
        target.write("\n")
    print("SEVEN_IMAGES_EXTERNAL_SOURCE_ATTESTED",output)

if __name__=="__main__":
    main()
