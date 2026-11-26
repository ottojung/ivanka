"""Retrospective truth-based diagnostic; never an assembler input.

Required env: IVANKA_OUTPUT_DIR (cap FASTAs), IVANKA_CASES_ROOT (reads),
IVANKA_TRUTH_ROOT (<case>/hidden-truth/haplotypes.fasta). All cap FASTAs for a
case are read and hash-verified against the pinned receipt before truth opens.
"""
import gzip
import hashlib
import json
import os
import pathlib

HERE = pathlib.Path(__file__).parent
RECEIPT = json.loads((HERE / "pinned_receipt.json").read_text())
COMP = str.maketrans("ACGT", "TGCA")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rc(seq):
    return seq.translate(COMP)[::-1]


def kmers(seq):
    return {min(seq[i:i + 31], rc(seq[i:i + 31]))
            for i in range(len(seq) - 30)
            if set(seq[i:i + 31]) <= set("ACGT")}


def fasta(path):
    return ["".join(l.strip() for l in b.splitlines() if not l.startswith(">"))
            for b in path.read_text().split(">")[1:]]


def required(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing required env {name}")
    return pathlib.Path(value)


def main():
    outputs = required("IVANKA_OUTPUT_DIR")
    cases_root = required("IVANKA_CASES_ROOT")
    truth_root = required("IVANKA_TRUTH_ROOT")
    rows = []
    for case in RECEIPT["predeclared_cases"]:
        contigs = {}
        for cap in RECEIPT["caps_tested"]:
            path = outputs / f"{case}.cap{cap}.fa"
            data = path.read_bytes()
            if sha(data) != RECEIPT["output_sha256"][f"{case}|{cap}"]:
                raise SystemExit(f"output hash mismatch: {case} cap {cap}")
            contigs[cap] = fasta(path)
        observed = set()
        reads = cases_root / case / "reads"
        for name in ("R1.fastq.gz", "R2.fastq.gz"):
            with gzip.open(reads / name, "rt") as fh:
                for i, line in enumerate(fh):
                    if i % 4 == 1:
                        observed |= kmers(line.strip().upper())
        is_jackpot = case.startswith("pcr_jackpot")
        truth = None
        if is_jackpot:
            truth = kmers(fasta(truth_root / case / "hidden-truth" / "haplotypes.fasta")[0]) & observed
        for cap, seqs in contigs.items():
            ck = set().union(*(kmers(s) for s in seqs))
            row = {"case": case, "cap": cap, "contigs": len(seqs),
                   "sequence_bases": sum(map(len, seqs)),
                   "contig_kmers_read_supported": len(ck & observed)}
            if truth is not None:
                row["truth31_in_reads"] = len(truth)
                row["truth31_recovered"] = len(ck & truth)
                row["truth31_fraction"] = round(row["truth31_recovered"] / len(truth), 4)
            rows.append(row)
            print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
