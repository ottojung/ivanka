use super::{spans, K};

const MIN_FLANK: usize = 800;
const MAX_VALLEY: usize = 200;
const MIN_DEPTH: u32 = 20;

/// A narrow, deep read-support valley between two long dense regions is an
/// assembler join only when original fragments also stop spanning it. All
/// inputs are read-derived from this candidate; no truth, reference, family
/// label or benchmark-tuned threshold is consulted. The reported span lets
/// the writer present both flanks as separate native subsequences instead of
/// inventing an adjacency or an orientation across the gap.
pub(in super::super) fn junction(
    depth: &[u32],
    pair_spans: &[(usize, usize)],
) -> Option<(usize, usize)> {
    if depth.len() < 2 * MIN_FLANK + MAX_VALLEY + K {
        return None;
    }
    let mut sorted = depth.to_vec();
    sorted.sort_unstable();
    let median = sorted[sorted.len() / 2];
    if median < MIN_DEPTH {
        return None;
    }
    let (high, low) = (median / 2, median / 5);
    let mut best: Option<(usize, usize, u32)> = None;
    let mut i = 0;
    while i < depth.len() {
        if depth[i] > high {
            i += 1;
            continue;
        }
        let start = i;
        while i < depth.len() && depth[i] <= high {
            i += 1;
        }
        let core = depth[start..i].iter().copied().min().unwrap_or(0);
        if i - start >= K
            && i - start <= MAX_VALLEY
            && start >= MIN_FLANK
            && depth.len() - i >= MIN_FLANK
            && core <= low
            && spans::dense(&depth[..start], high)
            && spans::dense(&depth[i..], high)
            && spans::unsupported(pair_spans, start, i)
            && best.is_none_or(|(_, _, seen)| core < seen)
        {
            best = Some((start, i, core));
        }
    }
    best.map(|(a, b, _)| (a, b))
}
