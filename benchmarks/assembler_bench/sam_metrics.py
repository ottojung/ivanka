"""Count per-primary-read SAM CIGAR soft clips without publishing read identities."""
import hashlib
import re
from pathlib import Path

CIGAR = re.compile(rb"([1-9][0-9]*)([MIDNSHP=X])")
READ_CONSUME = b"MIS=X"
SCHEMA = "assembler-bench.sam-primary-cigar.v1"


def _cigar_parts(value):
    parts = [(int(match[1]), match[2]) for match in CIGAR.finditer(value)]
    if not parts or b"".join(
            str(length).encode() + op for length, op in parts) != value:
        raise ValueError("invalid SAM CIGAR")
    soft = [i for i, (_, op) in enumerate(parts) if op == b"S"]
    visible = [i for i, (_, op) in enumerate(parts) if op != b"H"]
    if soft and any(i not in (visible[0], visible[-1]) for i in soft):
        raise ValueError("nonterminal soft clip in SAM CIGAR")
    return parts


def summarize_sam(path):
    """Metric denominator: mapped primary *alignment records*, not molecules."""
    path = Path(path)
    if not path.is_file():
        return {"schema": SCHEMA, "status": "unavailable",
                "reason": "SAM artifact not retained", "values": {}}
    counts = {key: 0 for key in (
        "records", "primary_mapped", "primary_unmapped",
        "secondary", "supplementary", "duplicates", "mapq_zero",
        "mapq_unknown", "read_bases", "aligned_read_bases",
        "inserted_bases", "deleted_reference_bases", "soft_clipped_reads",
        "soft_clip_events", "soft_clipped_bases", "left_clip_events",
        "right_clip_events", "left_clipped_bases", "right_clipped_bases",
        "soft_clip_length_max")}
    clip_lengths = []
    digest = hashlib.sha256()
    mapq_sum = 0
    mapped_with_mapq = 0
    try:
        with path.open("rb") as src:
            for line in src:
                digest.update(line)
                if line.startswith(b"@"):
                    continue
                fields = line.rstrip(b"\r\n").split(b"\t")
                if len(fields) < 11:
                    raise ValueError("invalid SAM record")
                try:
                    flag, mapq = int(fields[1]), int(fields[4])
                except ValueError as exc:
                    raise ValueError("invalid SAM flag or mapq") from exc
                if flag < 0 or not 0 <= mapq <= 255:
                    raise ValueError("out-of-range SAM flag or mapq")
                counts["records"] += 1
                if flag & 0x100:
                    counts["secondary"] += 1
                    continue
                if flag & 0x800:
                    counts["supplementary"] += 1
                    continue
                if flag & 0x4:
                    counts["primary_unmapped"] += 1
                    continue
                if fields[5] == b"*" or fields[9] == b"*":
                    raise ValueError("mapped primary lacks CIGAR or sequence")
                parts = _cigar_parts(fields[5])
                seq_length = len(fields[9])
                if sum(n for n, op in parts if op in READ_CONSUME) != seq_length:
                    raise ValueError("CIGAR and read sequence length disagree")
                counts["primary_mapped"] += 1
                counts["duplicates"] += bool(flag & 0x400)
                counts["mapq_zero"] += mapq == 0
                counts["mapq_unknown"] += mapq == 255
                if mapq != 255:
                    mapped_with_mapq += 1
                    mapq_sum += mapq
                counts["read_bases"] += seq_length
                counts["aligned_read_bases"] += sum(
                    n for n, op in parts if op in (b"M", b"=", b"X"))
                counts["inserted_bases"] += sum(
                    n for n, op in parts if op == b"I")
                counts["deleted_reference_bases"] += sum(
                    n for n, op in parts if op == b"D")
                clips = [n for n, op in parts if op == b"S"]
                if not clips:
                    continue
                counts["soft_clipped_reads"] += 1
                counts["soft_clip_events"] += len(clips)
                counts["soft_clipped_bases"] += sum(clips)
                clip_lengths.extend(clips)
                counts["soft_clip_length_max"] = max(
                    counts["soft_clip_length_max"], *clips)
                visible = [(n, op) for n, op in parts if op != b"H"]
                if visible[0][1] == b"S":
                    counts["left_clip_events"] += 1
                    counts["left_clipped_bases"] += visible[0][0]
                if len(visible) > 1 and visible[-1][1] == b"S":
                    counts["right_clip_events"] += 1
                    counts["right_clipped_bases"] += visible[-1][0]
    except (OSError, ValueError) as exc:
        return {"schema": SCHEMA, "status": "invalid",
                "reason": str(exc), "values": {}, "source_sha256": None}
    mapped = counts["primary_mapped"]
    read_bases = counts["read_bases"]
    total_primary = mapped + counts["primary_unmapped"]
    counts.update({
        "clipped_read_fraction": counts["soft_clipped_reads"] / mapped
        if mapped else None,
        "soft_clipped_bases_per_1000_read_bases":
            1000 * counts["soft_clipped_bases"] / read_bases
            if read_bases else None,
        "soft_clip_events_per_1000_primary_mapped":
            1000 * counts["soft_clip_events"] / mapped if mapped else None,
        "primary_mapped_fraction": mapped / total_primary
        if total_primary else None,
        "mean_known_mapq": mapq_sum / mapped_with_mapq
        if mapped_with_mapq else None,
        "mean_soft_clip_event_length": (
            sum(clip_lengths) / len(clip_lengths) if clip_lengths else None),
    })
    return {"schema": SCHEMA, "status": "measured",
            "source_sha256": digest.hexdigest(),
            "mapping_stage": "MiCall scratch/temp.sam",
            "denominators": {"mapped_primary_records": mapped,
                             "mapped_primary_read_bases": read_bases,
                             "all_primary_records": total_primary,
                             "mapq_observed_primary": mapped_with_mapq},
            "values": counts}


def public_diagnostics(folder):
    """Extract neutral MiCall evidence; no file path or read identity escapes."""
    from benchmarks.diagnostic_metrics import extract
    root = Path(folder)
    sam = summarize_sam(root / "scratch" / "temp.sam")
    nuc = extract(root)
    return {"schema": "assembler-bench.micall-diagnostics.v1",
            "mapping": sam,
            "micall_csv": {
                "values": nuc["values"],
                "context": {key: value for key, value in nuc["context"].items()
                            if key != "exact_coverage_selected_contig"},
                "unavailable": nuc["unavailable"], "errors": [
                    "MiCall diagnostic source invalid" for _ in nuc["errors"]]},
            "qualification_effect": "none"}
