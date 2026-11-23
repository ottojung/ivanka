# Experimental read-supported-span candidate ranking

**Status: unqualified experiment, not a benchmark success.**

Ivanka's initial ranking grants up to eight candidates priority by the
product of extension-read support and contig span, but historically sorts
those high-evidence candidates by support *density*. That can favour a
shorter repeat-collapsed path over a much longer, better-supported one.

The experiment sorts **only this preselected high-evidence group** by
`support × assembled bases`. All other candidates continue to use the
old support-density comparison. Protected same-sample input seeds still
have absolute precedence, and the native assembler takes no references
or hidden truths. This is a hypothesis about original read support,
not about reference alignability or scoring.

In the independently prepared HXB2-derived `clonal-s013` case, the
old density ranking selected a 9,597-nt candidate with 19,156
extension-read observations and a post-hoc, independent standalone
alignment score of 0. The alternative selected a 10,026-nt candidate
with 19,851 extension-read observations and a standalone score of
0.96728. These values were computed **after** contig assembly, using
the withholding-scoped benchmark scorer, not by the assembler.

An A/B screen of the preselected first seed from every synthetic family
produced 24 identical scored assemblies and one small regression
(homopolymer_slippage: −0.00733). This is not proof of a general win,
and the rescued case is not an untouched hold-out. More seeds, all
required MiCall output stages and original physical 198 must be
re-examined before considering merge. Nonidentifiability of repeat
phasing remains a biological limitation; see Issue #273.

**Never** grant this experiment reference sequence access or select its
parameters from hidden-truth results. Do not replace the existing
qualified Rust release or mark the seven-way Ψ gate passed.
