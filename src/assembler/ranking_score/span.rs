use std::cmp::Ordering;
use std::collections::HashSet;

// Within the high-evidence shortlist prefer total read-backed span.
// For other candidates retain the normalized support-density comparison.
pub(super) fn compare(
    favourite: bool,
    (a_reads, a_len): (usize, usize),
    (b_reads, b_len): (usize, usize),
) -> Ordering {
    let (a, b) = (a_reads as u128, b_reads as u128);
    let (x, y) = (a_len as u128, b_len as u128);
    if favourite {
        (b * y).cmp(&(a * x))
    } else {
        (b * x).cmp(&(a * y))
    }
}

// The shortlist is fixed by read evidence alone, never reference alignment.
pub(super) fn favourites(
    candidates: &[(usize, (Vec<u8>, usize))],
    n: usize,
    protected: usize,
) -> HashSet<usize> {
    let mut spans = candidates
        .iter()
        .filter(|(i, (_, reads))| *i >= protected && *reads > 0)
        .map(|(i, (seq, reads))| (*i, (*reads as u128) * (seq.len() as u128)))
        .collect::<Vec<_>>();
    spans.sort_unstable_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    spans
        .into_iter()
        .take(if candidates.len() > n.saturating_mul(2) {
            (n / 2).min(8)
        } else {
            0
        })
        .map(|(i, _)| i)
        .collect()
}
