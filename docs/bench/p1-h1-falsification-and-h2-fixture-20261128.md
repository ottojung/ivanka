# P1 H1 falsification and conservative H2 candidate (2026-11-28)

Owner: agent-FReJQGQODlgkArssDisF5g-wrought | host marceline-dev | issue 13mh3jxJbwPnB2hIZ9JdZx-blush.

Exact base for this increment: `fc27fb87b7febd76236fde3b18d9035e97fd9710` (the signed H1-falsification/fixture branch). This commit implements ONE conservative H2 source candidate on that branch, not on main. No image, frozen data, threshold, scorer, gate, truth or reference is changed; no native panel is run.

## H1 remains explicitly rejected

1. The duplicated-traversal signature exists in historical `12d8c72`, which has no native-fragment merge or fallback at all.
2. `native_fragments::select::retain` already skips candidates whose canonical 31-mers are represented (`represent::uncovered`); a covered fallback is either redundant or the only surviving evidence when a mate-tail 31-mer vetoes the merge.
3. Native `contigs.fasta` and MiCall `unstitched_contigs.fasta` are byte-identical in all five flagged cases, placing the duplication upstream of fragment ranking.

## H2 hypothesis and conservative implementation

Hypothesis: an approximate second traversal of one read-supported path can be extended without the exact-31-mer cycle stop (`CYCLE_MATCH = 512`). Sequence similarity alone is not enough to split it: a homologous repeat or a genuine tandem repeat can look similar. A split is justified only when there is *independent read-derived evidence of an unsupported transition* between two disjoint, read-supported approximate copies.

Review repairs on 2026-11-28: (a) similar-window endpoints are not a localized unsupported transition, so approximate-repeat rendering now emits the intervening read-supported middle as its own native fragment (`pieces_keep_middle`); a test proves the rendered intervals cover every base of the fixture and each is a native substring, so no depth-120 middle base is dropped. Localized depth-valley joins keep the existing two-flank rule. (b) `spans::seed` now builds the reverse complement from the opposite end; strand invariance is tested on an asymmetric word and a long path. (c) pair-support fixtures use varied short localized spans plus genuinely crossing pairs, not repeated copies of one wide interval. Promotion/experiment remains blocked until re-review.

Implementation (`read_backed/ranking/approximate.rs`, `spans.rs`, `related/render.rs`, `output.rs`):

- Two disjoint windows (generic 2000/1000 spacing, matching existing cycle spacing) are compared by canonical 12-mer seeds. Only positions with original-pair depth >= 3 contribute seeds, so the signal is read-derived.
- A candidate is raised only when the shared fraction is at least one quarter of the smaller seed set (250 per mille) **and** `spans::unsupported` finds far fewer original pairs crossing the boundary than comparable flanks **and** both flanks are read-supported (`spans::dense`). Those are the existing read-derived unsupported-join rules, not new fitted thresholds.
- `ranking::any_junction` prefers the established depth-valley join and otherwise applies this approximate-repeat gate. `output::component` still renders only native subsequences via existing `pieces()`/`tiling::present()`: no base is invented, reordered or removed, and a supported path is never cut on similarity alone.
- No genome length, truth, reference, family label, case name or tuning input is read. Existing golden byte-identity, clonal, tandem-repeat, distinct-haplotype and supported-join tests remain green.

Controls added: approximate repeat with no spanning pairs splits; the same approximate repeat with spanning original pairs stays whole; a genuine 150 bp tandem repeat stays whole; distinct haplotypes and a supported long clonal path stay whole.

## Predeclared ready experiment (requires explicit P1 grant)

1. No native panel, no worker, slot, podman, image, STOP/s6 or cohort replay in this turn. PX continues; the integrated retry belongs to cNcov and UNZbw grants slots.
2. When a short P1 slot is granted, run the already predeclared truth-free native panel on the five held-out residuals plus five negative controls with candidate `dabda459`+H2 versus baseline, alternating arms, OS limits, empty environment and truth opened only in a sealed posthoc.
3. Decision rule predeclared: H2 is supported only if the approximate-repeat split is observed on the read-derived residual fixtures with no change on supported homologous-repeat, tandem-repeat or clonal controls. Any control change is a stop, not a tuning opportunity.
4. Repeated-path per mille is a mechanism diagnostic only. Any production promotion still needs the separate integrated final-MAX evaluation; no qualification or clinical claim is made.
