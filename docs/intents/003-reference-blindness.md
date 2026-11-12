# Intent 003: Reference-blind assembly and candidate selection

**Status: existing non-negotiable requirement; retained without relaxation.**

Ivanka's input evidence is the original paired reads, with optional input
contigs that have been independently derived from **those same reads**.
Under the default MiCall/benchmark invocation in [Intent 002](002-default-invocation-parity.md),
no optional seeds or other additional arguments are supplied.

No known viral reference genome, HXB2 sequence, subtype/HCV reference, viral
reference panel, benchmark alignments, reference-guided 21-mer score, or
evaluation outcome may enter Ivanka or influence its assembly, ranking,
selection, trimming, tiling, or fallback logic. Using reference similarity to
select a contig is a scientific validity failure even if it increases Ψ.

MiCall may use references **downstream of finalized Ivanka FASTA output**;
the evaluator may use a fixed reference panel **solely after** candidates
are frozen. Neither may feed reference-conditioned information back into
Ivanka. The same rule applies to all alternative assemblers' candidate
selection and to all new synthetic benchmarking workflows.

**Acceptance:** static and integration guards enforce the reference boundary,
synthetic truth is withheld from every assembler, and human review checks
any new data path. A numerically successful but reference-guided run is
ineligible for qualification.

This intent retains the scientific boundary already established in
[AGENTS.md](../../AGENTS.md) and
[the assembly objective](../assembly-objective.md).
