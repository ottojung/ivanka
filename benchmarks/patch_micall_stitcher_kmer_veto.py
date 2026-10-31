#!/usr/bin/env python3
"""Experimental, fail-closed patch to MiCall's referenceless stitcher.

The candidate rejects an overlap/path merge if it drops canonical 31-mers
present in the contigs it consumes. The pinned IVA control image is unchanged.
"""
import importlib.util
from pathlib import Path


def patched_source(source):
    anchor = "\ndef try_combine_1(\n"
    helper = '''

def preserves_source_kmers(source_sequences, stitched_sequence, k=31):
    """Return False when a merge collapses canonical source k-mers.

    This is conservative sequence preservation, not validated phasing.
    """
    from micall.utils.exact_coverage import reverse_complement

    def kmers(seq):
        return {
            min(seq[i:i + k], reverse_complement(seq[i:i + k]))
            for i in range(max(0, len(seq) - k + 1))
            if set(seq[i:i + k]) <= {"A", "C", "G", "T"}
        }

    represented = kmers(stitched_sequence)
    for source in source_sequences:
        if len(source) < k:
            if (source not in stitched_sequence
                    and reverse_complement(source) not in stitched_sequence):
                return False
        elif not kmers(source).issubset(represented):
            return False
    return True

'''
    pairs = [
        (anchor, helper + anchor),
        ('''            if result is not None:
                combined, additional_score = result
                return first, second, combined''',
         '''            if result is not None:
                combined, additional_score = result
                if not preserves_source_kmers((first.seq, second.seq), combined.seq):
                    continue
                return first, second, combined'''),
        ('''        log(events.Constructed(most_probable))
        yield most_probable.whole
        remaining = tuple(''',
         '''        log(events.Constructed(most_probable))
        consumed = tuple(c for c in remaining if most_probable.has_contig(c))
        if preserves_source_kmers((c.seq for c in consumed), most_probable.whole.seq):
            yield most_probable.whole
        else:
            # A lossy proposed path must not erase a supported alternative.
            yield from consumed
        remaining = tuple('''),
    ]
    if "def preserves_source_kmers(" in source:
        raise ValueError("Refusing already-modified MiCall stitcher")
    pinned_three_field = (
        "            if result is not None:\n"
        "                combined, _additional_score, _covered_input = result\n"
        "                return first, second, combined"
    )
    patched_three_field = (
        "            if result is not None:\n"
        "                combined, _additional_score, _covered_input = result\n"
        "                if not preserves_source_kmers((first.seq, second.seq), combined.seq):\n"
        "                    continue\n"
        "                return first, second, combined"
    )
    if source.count(pairs[1][0]) == 1 and source.count(pinned_three_field) == 0:
        pass
    elif source.count(pairs[1][0]) == 0 and source.count(pinned_three_field) == 1:
        pairs[1] = (pinned_three_field, patched_three_field)
    else:
        raise ValueError("Unexpected MiCall try_combine_1 tuple contract")
    for old, new in pairs:
        if source.count(old) != 1:
            raise ValueError(f"Unexpected MiCall stitcher source shape near {old[:35]!r}")
        source = source.replace(old, new)
    compile(source, "referenceless_contig_stitcher.py", "exec")
    return source


def main():
    spec = importlib.util.find_spec("micall.utils.referenceless_contig_stitcher")
    if spec is None or spec.origin is None:
        raise RuntimeError("MiCall referenceless stitcher not installed")
    path = Path(spec.origin)
    source = path.read_text()
    patched = patched_source(source)
    path.write_text(patched)
    if path.read_text() != patched:
        raise RuntimeError("MiCall stitcher patch verification failed")
    print(f"PATCHED_REFERENCLESS_STITCHER_KMER_VETO {path}")


if __name__ == "__main__":
    main()
