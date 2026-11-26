# Equal-strain native evidence deficit — 2026-11-26

Post-assembly diagnostic of the completed prospective P1 candidate 12d8c72f.
For each abundant truth failing its existing 90% relative floor, compare
unstitched contigs with exact canonical 31-mers exclusive to that truth
(relative to the other truth) and observed in the original reads. The
comparator is the strongest successful rival by final MiCall score for
that truth, not a contig selected using truth.

All 16 equal-strain cases were examined. Sixteen abundant truths across
13 cases missed their relative floors. Their median exclusive-k-mer
recovery is 23.36% in Ivanka versus 96.81% in the strongest rival. Two
failing truths recover zero of these k-mers in Ivanka. This does not
establish long-range phase or independent-molecule support.

Reproduce with `python3 benchmarks/equal_strains_read_support.py` and
the same three root arguments used by the PCR-jackpot diagnostic, plus a
fresh `--output`. The retained report includes input SHA-256 digests and
aggregate counts only. No truth enters assembly, no threshold changes,
and no result is promoted or qualified.
