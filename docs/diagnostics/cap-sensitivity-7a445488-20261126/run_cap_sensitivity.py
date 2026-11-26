"""Reproduce the bounded 16/24/32 cap sensitivity from pinned receipts.

No private paths, no FASTQ/third-party data in this repository. Required env:
  IVANKA_BINARY       preserved binary (SHA256 must match pinned receipt)
  IVANKA_CASES_ROOT   root with <case>/reads/R{1,2}.fastq.gz and
                      <case>/assembly_*/seeds.fasta (original sample-derived)
  IVANKA_OUTPUT_DIR   writable directory for FASTA/stderr/JSON records
Truth is never opened here. Caps are invocation-only; the default remains 16.
"""
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import time

HERE = pathlib.Path(__file__).parent
RECEIPT = json.loads((HERE / "pinned_receipt.json").read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def env(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing required env {name}")
    return pathlib.Path(value)


def available_kb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            return int(line.split()[1])
    return 0


def main():
    binary = env("IVANKA_BINARY")
    root = env("IVANKA_CASES_ROOT")
    out_dir = env("IVANKA_OUTPUT_DIR")
    out_dir.mkdir(parents=True, exist_ok=True)
    deadline = float(os.environ.get("IVANKA_DEADLINE", "30"))
    low_mem = int(os.environ.get("IVANKA_LOW_MEM_KB", "4000000"))
    if sha(binary.read_bytes()) != RECEIPT["binary_sha256"]:
        raise SystemExit("binary SHA mismatch with pinned receipt")
    if available_kb() < low_mem:
        raise SystemExit("low memory at start")
    for case in RECEIPT["predeclared_cases"]:
        reads = root / case / "reads"
        seeds = sorted((root / case).glob("assembly_*/seeds.fasta"))
        if len(seeds) != 1:
            raise SystemExit(f"expected one seed for {case}, got {len(seeds)}")
        identities = RECEIPT["input_identity"][case]
        for key, path in (("R1", reads / "R1.fastq.gz"),
                          ("R2", reads / "R2.fastq.gz"), ("seed", seeds[0])):
            if sha(path.read_bytes()) != identities[key]:
                raise SystemExit(f"input hash mismatch: {case} {key}")
        for cap in RECEIPT["caps_tested"]:
            out = out_dir / f"{case}.cap{cap}.fa"
            err = out_dir / f"{case}.cap{cap}.err"
            cmd = [str(binary), "--reads1", str(reads / "R1.fastq.gz"),
                   "--reads2", str(reads / "R2.fastq.gz"), "--seeds", str(seeds[0]),
                   "--max-contigs", str(cap), "--output", str(out)]
            started = time.monotonic()
            with out.open("wb") as so, err.open("wb") as se:
                proc = subprocess.Popen(cmd, env={"PATH": "/usr/bin:/bin"},
                                        stdout=so, stderr=se)
                while True:
                    pid, status, usage = os.wait4(proc.pid, os.WNOHANG)
                    if pid:
                        break
                    if time.monotonic() - started > deadline:
                        os.kill(proc.pid, signal.SIGKILL)
                        _, status, usage = os.wait4(proc.pid, 0)
                        break
                    time.sleep(0.01)
            fasta = out.read_bytes()
            if sha(fasta) != RECEIPT["output_sha256"][f"{case}|{cap}"]:
                raise SystemExit(f"output hash mismatch: {case} cap {cap}")
            print(case, cap, os.waitstatus_to_exitcode(status),
                  round(time.monotonic() - started, 3), usage.ru_maxrss)


if __name__ == "__main__":
    main()
