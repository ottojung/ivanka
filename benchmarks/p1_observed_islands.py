"""Retrospective truth-position support islands; not assembly or qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import time

from contig_diversity import canonical_kmers, read_fasta
from pcr_jackpot_read_support import read_support
from p1_cross_context_triage import POSTHOC, pinned, require

K = 31
COMPLEMENT = str.maketrans("ACGT", "TGCA")
FAMILIES = ("pcr_jackpot", "coverage_hole")
MIN_DISK = 33 * 1024**3
MIN_CGROUP_HEADROOM = 1024**3
MAX_AS = 256 * 1024**2


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def guard():
    require(shutil.disk_usage("/workspace").free >= MIN_DISK, "disk reserve")
    cgroup = Path("/sys/fs/cgroup")
    limit = (cgroup / "memory.max").read_text().strip()
    current = int((cgroup / "memory.current").read_text())
    require(limit == "max" or int(limit) - current >= MIN_CGROUP_HEADROOM,
            "cgroup memory headroom")


def positions(sequence):
    require(len(sequence) >= K and set(sequence) <= set("ACGT"), "invalid truth sequence")
    return [min(w, w.translate(COMPLEMENT)[::-1])
            for w in (sequence[i:i + K] for i in range(len(sequence) - K + 1))]


def runs(mask):
    """Return lengths of all contiguous true and false window-position runs."""
    groups = {True: [], False: []}
    prior, length = None, 0
    for value in mask:
        value = bool(value)
        if prior is not None and value != prior:
            groups[prior].append(length)
            length = 0
        length += 1
        prior = value
    if prior is not None:
        groups[prior].append(length)
    return groups


def summarize(mask):
    group = runs(mask)
    observed, absent = group[True], group[False]
    return {"positions": len(mask), "supported_positions": sum(observed),
            "supported_runs": len(observed), "unsupported_runs": len(absent),
            "longest_supported_windows": max(observed, default=0),
            "longest_supported_bases": max(observed) + K - 1 if observed else 0,
            "longest_unsupported_windows": max(absent, default=0),
            "unsupported_runs_ge_31_windows": sum(n >= K for n in absent),
            "unsupported_runs_ge_150_windows": sum(n >= 150 for n in absent)}


def sources(row, data, output_root):
    case = row["case"]
    directory = data / case
    paths = [directory / "reads" / f"R{i}.fastq.gz" for i in (1, 2)]
    truth_path = directory / "hidden-truth/haplotypes.fasta"
    candidate = output_root / f"{case}.new.fa"
    # Bind both input mates, truth and exact already-sealed candidate output.
    require([digest(p) for p in paths] ==
            [row["input_sha256"][x] for x in ("R1", "R2")], "read digest drift")
    require(digest(candidate) == row["output_sha256"]["new"], "output digest drift")
    require(digest(truth_path) == row["input_sha256"]["truth"], "truth digest drift")
    return paths, truth_path, candidate


def case_report(row, data, output_root):
    case = row["case"]
    paths, truth_path, candidate = sources(row, data, output_root)
    sequences = read_fasta(truth_path)
    require(len(sequences) == len(row["panel"]) == 1, "unexpected truth panel")
    sequence = sequences[0]
    pos = positions(sequence)
    truth = set(pos)
    support = read_support(paths, truth)
    observed = set(support)
    output = set().union(*(canonical_kmers(s, K) for s in read_fasta(candidate)))
    panel = row["panel"][0]
    require(len(observed) == panel["observed_kmers"]
            and len(observed & output) == panel["recovered"]["new"],
            "prior native observed recovery disagrees")
    one = summarize([key in observed for key in pos])
    three = summarize([support[key] >= 3 for key in pos])
    recovered = summarize([key in observed and key in output for key in pos])
    require([digest(p) for p in paths] ==
            [row["input_sha256"][x] for x in ("R1", "R2")]
            and digest(candidate) == row["output_sha256"]["new"]
            and digest(truth_path) == row["input_sha256"]["truth"], "source changed")
    return {"case": case, "family": row["family"], "input_sha256": row["input_sha256"],
            "output_sha256": row["output_sha256"]["new"], "truth_length": len(sequence),
            "native_alignment_fraction": panel["native_alignment_fraction"]["new"],
            "observed_unique_kmers": len(observed), "recovered_unique_kmers": len(observed & output),
            "read_observed_position_runs": one,
            "three_distinct_read_string_position_runs": three,
            "recovered_observed_position_runs": recovered}


def envelope(record):
    return {"record": record, "record_sha256": hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()}


def check_record(record, row):
    require(record["case"] == row["case"] and record["family"] == row["family"]
            and record["input_sha256"] == row["input_sha256"]
            and record["output_sha256"] == row["output_sha256"]["new"],
            "checkpoint case identity")
    panel = row["panel"][0]
    require(record["native_alignment_fraction"] == panel["native_alignment_fraction"]["new"]
            and record["observed_unique_kmers"] == panel["observed_kmers"]
            and record["recovered_unique_kmers"] == panel["recovered"]["new"],
            "checkpoint prior panel disagreement")


def load_checkpoint(path, header, selected):
    if not path.exists():
        with path.open("x") as f:
            append(f, header)
        return []
    with path.open() as f:
        require(json.loads(f.readline()) == header, "checkpoint source/reader drift")
        records = []
        for line in f:
            require(line.endswith("\n"), "incomplete checkpoint line; preserve for inspection")
            item = json.loads(line)
            record = item["record"]
            require(item == envelope(record), "checkpoint record digest")
            require(len(records) < len(selected), "checkpoint extra case")
            check_record(record, selected[len(records)])
            records.append(record)
    return records


def append(stream, item):
    stream.write(json.dumps(item, sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("posthoc", "data", "output-root", "output", "checkpoint"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    require(not a.output.exists(), "output already exists")
    require(a.output.resolve() != a.checkpoint.resolve(), "output/checkpoint alias")
    resource.setrlimit(resource.RLIMIT_AS, (MAX_AS, MAX_AS))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    deadline = time.monotonic() + 240
    prior = json.loads(pinned(a.posthoc, POSTHOC))
    selected = [r for r in prior["cases"] if r["family"] in FAMILIES]
    require(len(selected) == 32 and len({r["case"] for r in selected}) == 32,
            "incomplete diagnostic cohort")
    header = {"schema": "ivanka.p1.observed-islands.checkpoint.v1",
              "posthoc_sha256": POSTHOC, "reader_sha256": digest(Path(__file__)),
              "case_order": [r["case"] for r in selected],
              "not_qualification": True}
    guard()
    records = load_checkpoint(a.checkpoint, header, selected)
    # Re-bind completed records to current immutable sources before resuming.
    for row in selected[:len(records)]:
        guard()
        require(time.monotonic() < deadline, "diagnostic deadline")
        sources(row, a.data, a.output_root)
    with a.checkpoint.open("a") as checkpoint:
        for row in selected[len(records):]:
            guard()
            require(time.monotonic() < deadline, "diagnostic deadline")
            record = case_report(row, a.data, a.output_root)
            append(checkpoint, envelope(record))
            records.append(record)
            print("observed-island diagnostic", len(records), "/32", flush=True)
    result = {"schema": "ivanka.p1.observed-islands.v1", "not_qualification": True,
              "source_posthoc_sha256": POSTHOC, "cases": records,
              "scope": "canonical truth-position 31-mer runs; not molecule or phase proof"}
    with a.output.open("x") as f:
        append(f, result)


if __name__ == "__main__":
    main()
