"""Reference-guided experimental Ivanka contig selection.

Ranks native contigs by exact 21-base matches to a *public*, pinned reference
panel. No IVA sample outputs or measured benchmark scores are read.
"""
import gzip
import hashlib
import json
from pathlib import Path

PANEL_SHA256 = "018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"
COMPLEMENT = str.maketrans("ACGT", "TGCA")


def index_references(references, k=21):
    if not 5 <= k <= 51:
        raise ValueError("Invalid reference k-mer size")
    index = set()
    for name, sequence in references:
        if not isinstance(name, str) or not isinstance(sequence, str):
            raise ValueError("Invalid reference entry")
        seq = sequence.upper()
        for i in range(len(seq)-k+1):
            part = seq[i:i+k]
            if set(part) <= set("ACGT"):
                index.add(part)
                index.add(part.translate(COMPLEMENT)[::-1])
    if not index:
        raise ValueError("Empty reference index")
    return index


def load_pinned_panel(path):
    data = gzip.decompress(Path(path).read_bytes())
    if hashlib.sha256(data).hexdigest() != PANEL_SHA256:
        raise ValueError("Pinned reference panel does not match checksum")
    refs = json.loads(data)
    if len(refs) != 33:
        raise ValueError("Unexpected reference panel size")
    return refs


def shared_reference_kmers(sequence, index, k=21):
    seq = sequence.upper()
    return sum(seq[i:i+k] in index for i in range(len(seq)-k+1))


def select_reference_supported(entries, limit, index, k=21):
    if not 1 <= limit <= 1000:
        raise ValueError("Invalid contig limit")
    hits = [shared_reference_kmers(seq, index, k) for _, seq in entries]
    order = sorted(range(len(entries)),
                   key=lambda i: (-hits[i], -len(entries[i][1]), i))
    return [entries[i] for i in order[:limit]], [hits[i] for i in order[:limit]]
