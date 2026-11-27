"""Read-only unique-anchor paired-read evidence across unobserved truth windows.

This does not infer a gap sequence or establish an assembly/qualification bound.
"""
import argparse
from collections import Counter
from functools import lru_cache
import gzip
from itertools import zip_longest
import json
from pathlib import Path
import resource
import time

from p1_observed_islands import (K, COMPLEMENT, FAMILIES, MAX_AS, POSTHOC,
                                 append, digest, envelope, guard, positions,
                                 sources)
from p1_cross_context_triage import pinned, require
from contig_diversity import read_fasta

MIN_GAP = 150


def reverse(seq):
    return seq.translate(COMPLEMENT)[::-1]


def fastq(path, mate):
    with gzip.open(path, "rt") as stream:
        while True:
            header = stream.readline()
            if not header:
                break
            seq = stream.readline().strip().upper()
            plus = stream.readline()
            qual = stream.readline().strip()
            fields = header.strip().split()
            require(len(fields) == 2 and fields[0].startswith("@")
                    and fields[1].split(":")[0] == str(mate)
                    and plus.startswith("+") and len(seq) == len(qual) > 0,
                    "invalid synthetic mate record")
            yield fields[0], seq


def paired(paths):
    for a, b in zip_longest(fastq(paths[0], 1), fastq(paths[1], 2)):
        require(a is not None and b is not None and a[0] == b[0],
                "mismatched mate identities")
        yield a[1], b[1]


def unique_index(truth):
    idx = {}
    repeated = set()
    for i in range(len(truth)-K+1):
        w = truth[i:i+K]
        for key, strand in ((w, 1), (reverse(w), -1)):
            if key in idx:
                repeated.add(key)
            else:
                idx[key] = (i, strand)
    return {w: v for w, v in idx.items() if w not in repeated}


def placement(seq, index):
    hits = []
    for j in range(len(seq)-K+1):
        found = index.get(seq[j:j+K])
        if found is None:
            continue
        i, strand = found
        start = i-j if strand == 1 else i-(len(seq)-K-j)
        hits.append((start, strand, i))
    if len({(p, s) for p, s, _ in hits}) != 1:
        return None
    lo = min(i for _, _, i in hits)
    hi = max(i for _, _, i in hits)
    if hi-lo < K:  # require two nonoverlapping unique anchors
        return None
    start, strand, _ = hits[0]
    return start, strand, lo, hi


def absent_runs(mask):
    start = None
    for i, value in enumerate(mask + [True]):
        if not value and start is None:
            start = i
        elif value and start is not None:
            if i-start >= MIN_GAP:
                yield start, i
            start = None


def bridges(first, second, gaps):
    if first is None or second is None:
        return ()
    left, right = sorted((first, second))
    if left[1] != 1 or right[1] != -1 or left[0] >= right[0]:
        return ()
    return tuple(i for i, (a,b) in enumerate(gaps) if left[3] < a and right[2] >= b)


def observed_from_pairs(paths, truth_keys, deadline):
    seen = set()
    counts = Counter()
    for n, pair in enumerate(paired(paths), 1):
        for seq in pair:
            if seq not in seen:
                seen.add(seq)
                for j in range(len(seq)-K+1):
                    w = seq[j:j+K]
                    key = min(w, reverse(w))
                    if key in truth_keys:
                        counts[key] += 1
        if n % 2048 == 0:
            guard()
            require(time.monotonic() < deadline, "diagnostic deadline")
    return set(counts)


def evaluate(row, data, output_root, deadline):
    paths, truth_path, candidate = sources(row, data, output_root)
    truths = read_fasta(truth_path)
    require(len(truths) == 1, "expected single truth")
    truth = truths[0]
    pos = positions(truth)
    observed = observed_from_pairs(paths, set(pos), deadline)
    require(len(observed) == row["panel"][0]["observed_kmers"],
            "prior observed kmer disagreement")
    gaps = list(absent_runs([p in observed for p in pos]))
    index = unique_index(truth)

    @lru_cache(maxsize=8192)
    def place(seq):
        return placement(seq, index)

    total, uniquely_anchored, spanning = 0, 0, 0
    pair_counts = [0]*len(gaps)
    distinct = [set() for _ in gaps]
    for first, second in paired(paths):
        total += 1
        x, y = place(first), place(second)
        if x is not None and y is not None:
            uniquely_anchored += 1
        hit = bridges(x, y, gaps)
        if hit:
            spanning += 1
        for i in hit:
            pair_counts[i] += 1
            distinct[i].add((first, second))
        if total % 2048 == 0:
            guard()
            require(time.monotonic() < deadline, "diagnostic deadline")
    require(total > 0, "empty reads")
    sources(row, data, output_root)
    return {"case": row["case"], "family": row["family"],
            "input_sha256": row["input_sha256"],
            "output_sha256": digest(candidate), "pair_records": total,
            "both_mates_uniquely_anchored": uniquely_anchored,
            "pairs_spanning_any_gap": spanning,
            "gaps": [{"start_window": a, "end_window_exclusive": b,
                      "unsupported_windows": b-a, "inward_spanning_pairs": pair_counts[i],
                      "distinct_ordered_read_string_pairs": len(distinct[i])}
                     for i,(a,b) in enumerate(gaps)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("posthoc", "data", "output-root", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    a = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (MAX_AS, MAX_AS))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    deadline = time.monotonic()+240
    prior = json.loads(pinned(a.posthoc, POSTHOC))
    rows = [r for r in prior["cases"] if r["family"] in FAMILIES]
    require(len(rows) == 32 and len({r["case"] for r in rows}) == 32, "case roster")
    guard()
    with a.output.open("x") as f:
        append(f, {"schema": "ivanka.p1.pair-spanning.v1", "not_qualification": True,
                   "posthoc_sha256": POSTHOC, "reader_sha256": digest(Path(__file__)),
                   "case_order": [r["case"] for r in rows],
                   "scope": "strict unique 31mer anchors; no claim of absent linkage from zero"})
        for r in rows:
            guard()
            require(time.monotonic() < deadline, "diagnostic deadline")
            append(f, envelope(evaluate(r, a.data, a.output_root, deadline)))
            print(r["case"], flush=True)


if __name__ == "__main__":
    main()
