"""Strict two-mate original FASTQ reading. Read IDs never leave this module."""
import gzip
from pathlib import Path


def _open(path):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt")
    return Path(path).open()


def _name(header, mate):
    if not header.startswith("@"):
        raise ValueError("Malformed FASTQ original mate identifier")
    tokens = header[1:].strip().split()
    if not tokens:
        raise ValueError("Missing original FASTQ read-pair ID")
    identity = tokens[0]
    if identity.endswith(("/1", "/2")):
        if not identity.endswith("/" + str(mate)):
            raise ValueError("Wrong original mate order")
        identity = identity[:-2]
    if len(tokens) > 1 and tokens[1][:2] in ("1:", "2:"):
        if not tokens[1].startswith(str(mate) + ":"):
            raise ValueError("Inconsistent original mate designator")
    return identity


def _record(stream):
    head = stream.readline()
    if not head:
        return None
    seq = stream.readline().strip().upper()
    plus = stream.readline()
    qual = stream.readline().rstrip("\n\r")
    if (not plus.startswith("+") or not seq or len(seq) != len(qual)
            or set(seq) - set("ACGTN") or any(
                not 33 <= ord(c) <= 126 for c in qual)):
        raise ValueError("Malformed original paired FASTQ")
    return head, (seq, qual)


def iter_original_pairs(path1, path2, *, max_pairs=50000):
    with _open(path1) as mate1, _open(path2) as mate2:
        for _ in range(max_pairs):
            first, second = _record(mate1), _record(mate2)
            if (first is None) != (second is None):
                raise ValueError("Unequal original FASTQ mate counts")
            if first is None:
                return
            id1, id2 = _name(first[0], 1), _name(second[0], 2)
            if not id1 or id1 != id2:
                raise ValueError("Original paired FASTQ identities disagree")
            yield id1, first[1], second[1]
