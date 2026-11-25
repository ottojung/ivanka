#!/usr/bin/env python3
"""Read-only recomputation of the P0 contig-density / remap-latency figures
from RETAINED extracted scratch artifacts.

The original analyze_pairs.py streams `scratch.tar.gz`; those archives were
promoted to `retained-scratch/` and the archives removed on 2026-11-24, so the
original script can no longer compute the scratch metrics. This variant reads
the retained members (assembly contigs.fasta, seeds.fasta, assembler.log) and
otherwise reproduces the original statistics verbatim.

It never modifies a case directory, never reads a reference genome and never
reads an evaluator score to steer any assembly decision. All paired runtime
figures here are EXPLORATORY diagnostics: the IVA arm used the unauthorized
new-common-MiCall source and is not usable for P0 qualification.
"""
import argparse
import glob
import json
import os
import re
import statistics as st
from datetime import datetime

FMT = "%Y-%m-%d %H:%M:%S,%f"
MASK = (1 << 62) - 1
DIGIT = {"A": 0, "C": 1, "G": 2, "T": 3}
COMP = str.maketrans("ACGT", "TGCA")


def kmer_key(s):
    f = r = 0
    for b in s:
        d = DIGIT.get(b)
        if d is None:
            return None
        f = ((f << 2) & MASK) | d
        r = (r >> 2) | ((3 - d) << 60)
    return min(f, r)


def kmers(s):
    return {kmer_key(s[i:i + 31]) for i in range(len(s) - 30)}


def read_fasta(txt):
    out, name, seq = [], None, []
    for line in txt.splitlines():
        if line.startswith(">"):
            if name is not None:
                out.append((name, "".join(seq)))
            name, seq = line[1:].split()[0], []
        elif name is not None:
            seq.append(line.strip())
    if name is not None:
        out.append((name, "".join(seq)))
    return out


def read_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def read_text(path):
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def remap_seconds(txt):
    stages = []
    for line in txt.splitlines():
        m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+).*Running (\S+) on Sample", line)
        if m:
            stages.append((datetime.strptime(m.group(1), FMT), m.group(2)))
    for i, (t, name) in enumerate(stages):
        if name == "remap" and i + 1 < len(stages):
            return (stages[i + 1][0] - t).total_seconds()
    return None


def stderr_metrics(txt):
    d = {}
    m = re.search(r"Assembled (\d+) contigs in 0:00:([\d.]+)", txt)
    if m:
        d["assembled"] = int(m.group(1))
        d["assembly_seconds"] = float(m.group(2))
    m = re.search(r"(\d+) pairs reached the Bowtie2 -k 12 reporting limit", txt)
    d["bowtie_k12"] = int(m.group(1)) if m else 0
    d["stitcher_overlaps"] = len(re.findall(r"Ignoring coverage comparison for contig", txt))
    d["remap_seconds"] = remap_seconds(txt)
    return d


def scratch_metrics(root):
    """Same overlap classification as the original script, from retained files."""
    d = {"near85": 0, "near95": 0, "distinct": 0, "seeds": 0}
    roots = sorted(glob.glob(os.path.join(root, "assembly_*")))
    if not roots:
        return d
    ar = roots[0]
    log = read_text(os.path.join(ar, "assembler.log"))
    if not log:
        log = read_text(os.path.join(ar, "iva_out", "info.txt"))
    candidates = [os.path.join(ar, "contigs.fasta"),
                  os.path.join(ar, "iva_out", "contigs.fasta")]
    fasta = next((read_text(p) for p in candidates if os.path.exists(p)), "")
    sfasta = read_text(os.path.join(ar, "seeds.fasta"))
    q = re.search(r"IVANKA_QUALITY reported=(\d+) kmer_redundant=(\d+) "
                  r"no_extension_support=(\d+) snv_audit_candidates=(\d+)", log)
    if q:
        d.update(reported=int(q.group(1)), kmer_redundant=int(q.group(2)),
                 no_extension_support=int(q.group(3)), snv=int(q.group(4)))
    contigs, seeds = read_fasta(fasta), read_fasta(sfasta)
    d["contigs"] = len(contigs)
    seed_names = {name for name, _ in seeds}
    seed_km = set()
    for _, seq in seeds:
        seed_km |= kmers(seq)
    represented = set()
    ordered = [i for i, (n, _) in enumerate(contigs) if n in seed_names]
    ordered += [i for i in range(len(contigs)) if i not in ordered]
    for i in ordered:
        ks = kmers(contigs[i][1])
        frac = len(ks & represented) / len(ks) if ks else 0
        is_seed = contigs[i][0] in seed_names
        if is_seed:
            d["seeds"] += 1
        elif frac >= 0.95:
            d["near95"] += 1
        elif frac >= 0.85:
            d["near85"] += 1
        else:
            d["distinct"] += 1
        represented |= ks
    return d


def pair(base, sha):
    row = {"sha": sha}
    for lab, folder in (("ivanka", "p0-physical-selective-cases"),
                        ("iva", "p0-physical-updated-micall-iva-cases")):
        case = os.path.join(base, folder, sha)
        timing = read_json(os.path.join(case, "micall_internal_timing.json")) or {}
        row[lab + "_seconds"] = timing.get("seconds")
        row[lab + "_stderr"] = stderr_metrics(
            read_text(os.path.join(case, "podman.stderr.log")))
        retained = os.path.join(case, "retained-scratch")
        row[lab + "_scratch"] = (
            scratch_metrics(retained) if os.path.isdir(retained) else {})
    return row


def corr(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (
        (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="/workspace/ivanka-p0-prospective-allprojects-20261122")
    ap.add_argument("--out", default="/tmp/opencode/p0-retained-analysis.json")
    args = ap.parse_args()
    iv = {os.path.basename(os.path.dirname(f)) for f in
          glob.glob(os.path.join(args.base, "p0-physical-selective-cases", "*",
                                 "prospective-execution.json"))}
    iva = {os.path.basename(os.path.dirname(f)) for f in
           glob.glob(os.path.join(args.base, "p0-physical-updated-micall-iva-cases", "*",
                                  "prospective-execution.json"))}
    rows = [pair(args.base, sha) for sha in sorted(iv & iva)]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"schema": "ivanka.p0.contig-density-retained-analysis.v1",
                   "pairs": len(rows), "rows": rows}, fh, indent=2)
    ok = [r for r in rows if all(r[lab + "_seconds"] is not None and
                                 r[lab + "_stderr"].get("remap_seconds") is not None
                                 and r[lab + "_scratch"].get("contigs") is not None
                                 for lab in ("ivanka", "iva"))]
    remap_excess = [r["ivanka_stderr"]["remap_seconds"] - r["iva_stderr"]["remap_seconds"]
                    for r in ok]
    total_excess = [r["ivanka_seconds"] - r["iva_seconds"] for r in ok]
    ctg_excess = [r["ivanka_scratch"]["contigs"] - r["iva_scratch"]["contigs"]
                  for r in ok]
    print("pairs", len(rows), "timed+contiged", len(ok))
    print("Ivanka remap slower", sum(x > 0 for x in remap_excess), "/", len(ok))
    print("mean remap excess %.4fs; total excess %.4fs"
          % (st.mean(remap_excess), st.mean(total_excess)))
    print("corr(remap excess, total excess) %.6f" % corr(remap_excess, total_excess))
    print("corr(contig excess, remap excess) %.6f" % corr(ctg_excess, remap_excess))
    print("Ivanka contigs total", sum(r["ivanka_scratch"].get("contigs", 0) for r in rows),
          "IVA contigs total", sum(r["iva_scratch"].get("contigs", 0) for r in rows))
    print("Ivanka near85 total", sum(r["ivanka_scratch"].get("near85", 0) for r in rows))
    print("Ivanka k12 cases", sum(r["ivanka_stderr"].get("bowtie_k12", 0) > 0 for r in rows),
          "IVA k12 cases", sum(r["iva_stderr"].get("bowtie_k12", 0) > 0 for r in rows))
    print("Ivanka stitch warnings total",
          sum(r["ivanka_stderr"].get("stitcher_overlaps", 0) for r in rows),
          "IVA stitch warnings total",
          sum(r["iva_stderr"].get("stitcher_overlaps", 0) for r in rows))
    print("kmer_redundant total",
          sum(r["ivanka_scratch"].get("kmer_redundant", 0) for r in rows),
          "no_extension_support total",
          sum(r["ivanka_scratch"].get("no_extension_support", 0) for r in rows))


if __name__ == "__main__":
    main()
