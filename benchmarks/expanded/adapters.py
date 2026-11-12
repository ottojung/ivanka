"""Read-derived CLI contracts for seven independently executed assemblers.

No hidden scoring information or truth may enter any assembler.
Every result records the actual invocation and executable SHA256.
"""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ASSEMBLERS = ("ivanka", "iva", "haploflow", "megahit",
              "abyss", "spades", "velvet")
PROGRAMS = {
    "ivanka": ("ivanka",),
    "iva": ("iva",),
    "haploflow": ("haploflow",),
    "megahit": ("megahit",),
    "abyss": ("abyss-pe",),
    "spades": ("spades.py",),
    "velvet": ("velveth", "velvetg"),
}


def binary_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def require_programs(names=ASSEMBLERS, paths=None):
    """Fail closed on unavailable tools, never skip unfavorable competitors."""
    found = {}
    for assembler in names:
        if assembler not in PROGRAMS:
            raise ValueError("unknown assembler: " + assembler)
        found[assembler] = {}
        for program in PROGRAMS[assembler]:
            executable = (paths or {}).get(program) or shutil.which(program)
            if not executable or not Path(executable).is_file():
                raise FileNotFoundError(f"required tool not installed: {program}")
            absolute = Path(executable).resolve()
            found[assembler][program] = {
                "path": str(absolute), "sha256": binary_hash(absolute),
            }
    return found


def interleave_fastq(left, right, destination):
    """Haploflow accepts one FASTQ: provide BOTH mates, preserving order."""
    def open_reads(path):
        return gzip.open(path, "rt") if str(path).endswith(".gz") else open(path)
    with (open_reads(left) as r1, open_reads(right) as r2,
          Path(destination).open("x") as dest):
        while True:
            a = [r1.readline() for _ in range(4)]
            b = [r2.readline() for _ in range(4)]
            if not a[0] and not b[0]:
                break
            if not a[0] or not b[0] or not a[1] or not b[1]:
                raise ValueError("paired FASTQ has truncated or unpaired records")
            if (not a[0].startswith("@") or not b[0].startswith("@")
                    or not a[2].startswith("+") or not b[2].startswith("+")
                    or len(a[1].rstrip()) != len(a[3].rstrip())
                    or len(b[1].rstrip()) != len(b[3].rstrip())):
                raise ValueError("invalid paired FASTQ")
            dest.writelines(a)
            dest.writelines(b)


def steps(name, r1, r2, work, binaries, *, threads=2, insert_size=270):
    """Explicit argv lists, no shell execution or benchmark-truth arguments."""
    if name not in ASSEMBLERS or threads < 1 or insert_size < 1:
        raise ValueError("unsupported assembler configuration")
    r1, r2, work = Path(r1).resolve(), Path(r2).resolve(), Path(work).resolve()
    def exe(program):
        return binaries[name][program]["path"]
    if name == "ivanka":
        out = work / "contigs.fasta"
        return [[exe("ivanka"), "--reads1", str(r1), "--reads2",
                 str(r2), "--output", str(out)]], out
    if name == "iva":
        out = work / "iva" / "contigs.fasta"
        return [[exe("iva"), "-f", str(r1), "-r", str(r2),
                 "-t", str(threads), str(work / "iva")]], out
    if name == "haploflow":
        single = work / "both_mates.fastq"
        interleave_fastq(r1, r2, single)
        out = work / "haploflow" / "contigs.fa"
        return [[exe("haploflow"), "--read-file", str(single),
                 "--out", str(work / "haploflow"), "--filter", "100",
                 "--strict", "0"]], out
    if name == "megahit":
        out = work / "megahit" / "final.contigs.fa"
        return [[exe("megahit"), "-1", str(r1), "-2", str(r2),
                 "-t", str(threads), "-o", str(work / "megahit")]], out
    if name == "abyss":
        out = work / "assembly-contigs.fa"
        return [[exe("abyss-pe"), "k=41", "B=128M", "j=2",
                 "name=assembly", f"in={r1} {r2}"]], out
    if name == "spades":
        out = work / "spades" / "contigs.fasta"
        return [[exe("spades.py"), "-1", str(r1), "-2", str(r2),
                 "--phred-offset", "33", "-t", str(threads),
                 "-o", str(work / "spades")]], out
    out = work / "velvet" / "contigs.fa"
    return [[exe("velveth"), str(work / "velvet"), "31", "-fastq.gz",
             "-shortPaired", "-separate", str(r1), str(r2)],
            [exe("velvetg"), str(work / "velvet"), "-ins_length",
             str(insert_size), "-exp_cov", "auto"]], out


def execute(name, r1, r2, output_dir, binaries, *, threads=2, timeout=1800):
    """Run in an independent workspace; failure is never treated as a win."""
    if timeout <= 0:
        raise ValueError("positive timeout required")
    work = Path(output_dir)
    work.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    records = []
    # Include input transformation (Haploflow paired FASTQ interleaving)
    # in measured runtime. No competitor gets free preprocessing.
    result = {"assembler": name, "binary_provenance": binaries[name],
              "commands": [], "fasta": None,
              "status": "failed", "elapsed_wall_seconds": None}
    try:
        commands, fasta = steps(name, r1, r2, work, binaries, threads=threads)
        result["commands"], result["fasta"] = commands, str(fasta)
        for argv in commands:
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, timeout)
            # MiCall gives the wrapper an empty environment. External tools
            # may need a fixed executable search path for internal helpers.
            # Native Ivanka itself must always execute with truly empty env.
            child_env = {} if name == "ivanka" else {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
            }
            response = subprocess.run(
                argv, cwd=work, capture_output=True, text=True,
                timeout=remaining, check=False, env=child_env,
            )
            records.append({"returncode": response.returncode,
                            "stdout_tail": response.stdout[-1000:],
                            "stderr_tail": response.stderr[-2000:]})
            if response.returncode:
                result["error"] = f"assembler exited {response.returncode}"
                break
        else:
            if not fasta.is_file():
                result["error"] = "successful process produced no FASTA"
            else:
                if any(binary_hash(v["path"]) != v["sha256"]
                       for v in binaries[name].values()):
                    result["error"] = "executable changed during benchmark"
                else:
                    result["status"] = "success"
                    result["output_sha256"] = binary_hash(fasta)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["elapsed_wall_seconds"] = round(time.monotonic()-start, 6)
    result["steps"] = records
    (work / "execution.json").write_text(json.dumps(result, indent=2,
                                                     sort_keys=True)+"\n")
    return result
