"""Serialize experimental exact-template multi-mappings without breaking MiCall mates.

Only consume candidate pairs from exact_pair_remap_equivalence.compatible_copies.
Additional mappings are NOT additional molecules or haplotype-specific support.
This module never edits the original MiCall remap file.
"""
import csv
from collections import Counter, defaultdict

from exact_pair_remap_equivalence import reverse_complement

BAD_FLAGS = 0x4 | 0x8 | 0x100 | 0x800


def mate_number(row):
    flag = int(row["flag"])
    if (flag & BAD_FLAGS) or (flag & 3) != 3:
        raise ValueError("Unmapped, secondary, supplementary or unpaired read")
    read1, read2 = bool(flag & 0x40), bool(flag & 0x80)
    if read1 == read2:
        raise ValueError("Exactly one mate identity bit is required")
    return 1 if read1 else 2


def original_orientation(row):
    seq, qual = row["seq"].upper(), row["qual"]
    if not seq or len(seq) != len(qual) or set(seq) - set("ACGT"):
        raise ValueError("Invalid unambiguous read and quality")
    if int(row["flag"]) & 0x10:
        return reverse_complement(seq), qual[::-1]
    return seq, qual


def checked_pair(rows, qname, reference, original=None):
    if len(rows) != 2:
        raise ValueError("Alternative must contain exactly one mate pair")
    if any(row["qname"] != qname or row["rname"] != reference for row in rows):
        raise ValueError("Mismatched qname or reference")
    identities = [mate_number(row) for row in rows]
    if sorted(identities) != [1, 2]:
        raise ValueError("Duplicate mate identity")
    by_mate = dict(zip(identities, rows))
    a, b = by_mate[1], by_mate[2]
    for read, mate in ((a, b), (b, a)):
        if read["rnext"] not in ("=", reference):
            raise ValueError("Invalid mate reference")
        if int(read["pnext"]) != int(mate["pos"]) or int(read["pos"]) < 1:
            raise ValueError("Incorrect pair coordinates")
        flag, mate_flag = int(read["flag"]), int(mate["flag"])
        if bool(flag & 0x20) != bool(mate_flag & 0x10):
            raise ValueError("Inconsistent mate strand")
        if not read["cigar"].endswith("M") or read["cigar"][:-1] != str(len(read["seq"])):
            raise ValueError("Only exact full-length M alignments are eligible")
        if original is not None:
            source = original[mate_number(read)]
            if original_orientation(read) != original_orientation(source):
                raise ValueError("Alternative changes observed sequence or qualities")
            if read["cigar"] != source["cigar"]:
                raise ValueError("Alternative changes the observed CIGAR")
            if read["mapq"] != "0":
                raise ValueError("Alternative must mark MAPQ=0")
    return a, b


def serialize_pairs(original_rows, alternative_rows, output):
    """Insert each validated alternate pair after its last original mate.

    MiCall matches consecutive appearances of each qname, not qname+reference.
    Contiguous inserted pair records preserve the original pairing and prevent
    cross-reference pair loss. Validate ALL candidates before writing anything.
    """
    originals, alternatives = list(original_rows), list(alternative_rows)
    if not originals:
        raise ValueError("No original remap rows")
    fields = tuple(originals[0])
    if any(set(row) != set(fields) for row in originals + alternatives):
        raise ValueError("Different SAM CSV field sets")
    occurrences = Counter(row["qname"] for row in originals)
    original_by_name = defaultdict(list)
    for row in originals:
        original_by_name[row["qname"]].append(row)
    targets = defaultdict(list)
    for row in alternatives:
        targets[(row["qname"], row["rname"])].append(row)
    append_after = defaultdict(list)
    for (name, target), pair in sorted(targets.items()):
        source_pair = original_by_name.get(name, ())
        if occurrences[name] != 2:
            raise ValueError("Cannot augment absent or nonunique original pair")
        original_reference = source_pair[0]["rname"]
        if target == original_reference:
            raise ValueError("Alternative repeats original reference")
        source = checked_pair(source_pair, name, original_reference)
        candidate = checked_pair(pair, name, target, {1:source[0], 2:source[1]})
        append_after[name].extend(candidate)
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in originals:
        writer.writerow(row)
        occurrences[row["qname"]] -= 1
        if occurrences[row["qname"]] == 0:
            writer.writerows(append_after.get(row["qname"], ()))
    return {"original_rows":len(originals),
            "alternative_pairs":len(targets),
            "added_mapping_rows":len(alternatives),
            "new_read_pair_ids":0}
