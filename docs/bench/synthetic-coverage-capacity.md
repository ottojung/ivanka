# Synthetic read-depth capacity audit

This is a **read-only diagnostic**, not an alternate score, a cohort
exclusion, or a qualification gate. It does not provide truth sequences
or known references to an assembler.

The pinned MiCall fork at
[commit 5f054078](https://github.com/ottojung/MiCall/blob/5f054078e9720a5fa252b6467982e12624ca6d2b/micall/core/aln2counts.py)
sets the consensus minimum depth to **100**. Ordinary conseq.csv rows
require at least that coverage at an emitted position.

For a synthetic sample with N original read pairs, read length L and
dominant truth length G, the maximum possible **mean sequenced-base
coverage** even if every read targets the dominant genome, and every
base maps once, is 2NL/G. This bounds the genome-wide mean depth, not
the peak depth at any particular position. It does **not** imply that
all consensus rows must be empty: uneven coverage can produce short
islands above 100.

The pinned HXB2-derived cohort contains 400 cases. All **16 cases**
in the low_depth family have 2,500 pairs of 150-base reads for a
genome of approximately 9,600 bases. Their capacity is about 78x,
below the 100x MiCall threshold. Other families have a nominal
capacity above that threshold. This does **not** prove the other
families pass or that these 16 cannot yield a short consensus.

An independent, untouched IVA control using low_depth-s001 and
the pinned IVA image
b0f466d4f274e54828b1bd8b7fb4d225a6ff2a9b8269ab4029018a2b52545f45
finished integrated MiCall with exit code 0, but the evaluator
correctly reported no final MAX consensus. The existing pinned
Ivanka runs show the same outcome. This supports a shared reporting
limitation, not an isolated assembly failure.

In the same Ivanka run, the longest final unstitched contig has **9,634
bases**, and is an *exact substring* of the 9,657-base generating
genome. Independent contig-to-truth local alignment scores 9,634,
while the mandatory *final MiCall consensus* is absent, scoring 0.
The contig analysis is **diagnostic only**, never a replacement for
final MiCall scoring. Source evidence: unstitched_contigs.csv SHA-256
677786dad6c1d5e4e0d29e194c02ba7a2064e6dfe1efa61d11e874a33b416bde;
generating-truth FASTA SHA-256
90d5424a7934f57d1bb3efea581910afdd599bd574bc0a5e0f631886e9594a92.
The independent IVA control's execution.json SHA-256 was
b8438e86bfd2b309158a1855ea84a472564b427a12578989a0bf8e3b671ffb93.

For a reproducible independent audit, execute:

    PYTHONPATH=.:benchmarks python3 -m benchmarks.expanded.coverage_capacity \
      --cohort /path/to/pinned/hxb2/cohort \
      --micall /path/to/pinned/MiCall/fork \
      --output /path/to/report.json

The audit verifies original R1/R2 compressed-read digests,\ngenerating-truth hashes, manifest hashes and the MiCall source
threshold; its schema explicitly records qualification as
NOT_EVALUATED. An assembler outcome requires a separate authentic
MiCall run and source-pinned final-output scoring. Never infer a
passing score from the capacity estimate, substitute a contig for
MiCall's final consensus, or conceal a failed arm.

Do not silently modify frozen reads, the shared 100x threshold,
or acceptance requirements. Any new shared MiCall configuration
requires a fresh attested comparison of **all seven** dedicated
assemblers.
