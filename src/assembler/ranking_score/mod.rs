use std::collections::HashSet;

pub(super) fn ranked_candidates(
    seqs: Vec<Vec<u8>>,
    counts: Vec<usize>,
    n: usize,
    protected: usize,
) -> Vec<(usize, (Vec<u8>, usize))> {
    assert_eq!(seqs.len(), counts.len());
    let mut candidates = seqs.into_iter().zip(counts).enumerate().collect::<Vec<_>>();
    let mut spans = candidates
        .iter()
        .filter(|(i, (_, reads))| *i >= protected && *reads > 0)
        .map(|(i, (seq, reads))| (*i, (*reads as u128) * (seq.len() as u128)))
        .collect::<Vec<_>>();
    spans.sort_unstable_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    let span_favorites = spans
        .into_iter()
        .take(if candidates.len() > n.saturating_mul(2) {
            (n / 2).min(8)
        } else {
            0
        })
        .map(|(i, _)| i)
        .collect::<HashSet<_>>();
    candidates.sort_unstable_by(|a, b| {
        let a_span = span_favorites.contains(&a.0);
        let b_span = span_favorites.contains(&b.0);
        let a_protected = a.0 < protected;
        let b_protected = b.0 < protected;
        // High-evidence shortlist: favour supported span before density;
        // lower-ranked candidates keep the legacy per-base density order.
        b_protected
            .cmp(&a_protected)
            .then_with(|| b_span.cmp(&a_span))
            .then_with(|| {
                span::compare(
                    a_span && b_span,
                    (a.1 .1, a.1 .0.len()),
                    (b.1 .1, b.1 .0.len()),
                )
            })
            .then_with(|| b.1 .1.cmp(&a.1 .1))
            .then_with(|| b.1 .0.len().cmp(&a.1 .0.len()))
            .then_with(|| a.1 .0.cmp(&b.1 .0))
    });
    candidates
}

#[cfg(test)]
use super::ranking::select_supported_contigs;

// Variant-specific evidence is separate from the primary ranking score.
mod snv;
mod span;
pub(super) use snv::supported_snv_alternative;

#[cfg(test)]
mod tests;
