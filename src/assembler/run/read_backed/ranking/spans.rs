/// Count original pairs that reach an interval from either flank. A mate that
/// stops inside the valley still evidences local continuity, so it counts as
/// spanning evidence too; this avoids declaring a join from incomplete spans.
pub(in super::super) fn spanning(spans: &[(usize, usize)], a: usize, b: usize) -> usize {
    spans
        .iter()
        .filter(|&&(lo, hi)| (lo <= a && hi >= a) || (lo <= b && hi >= b))
        .count()
}

/// A depth valley alone can be a genuine connected molecule. Require far
/// fewer spanning fragments than in comparable nearby dense intervals before
/// declaring an unsupported assembler join. The baseline and ratio are
/// computed only from this candidate's original read pairs: no truth,
/// reference, family label or benchmark-fitted threshold is consulted.
pub(in super::super) fn unsupported(spans: &[(usize, usize)], a: usize, b: usize) -> bool {
    let width = b - a;
    let before = spanning(spans, a.saturating_sub(width + 600), a.saturating_sub(600));
    let after = spanning(spans, b + 600, b + 600 + width);
    let baseline = before.max(after);
    baseline >= 20 && spanning(spans, a, b) * 4 <= baseline
}

/// At least ninety percent of a flank must carry original-pair depth.
pub(in super::super) fn dense(depth: &[u32], high: u32) -> bool {
    depth.iter().filter(|&&v| v >= high).count() * 100 >= depth.len() * 90
}
