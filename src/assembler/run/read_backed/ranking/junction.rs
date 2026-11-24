use super::K;

const MIN_FLANK: usize = 800;
const MAX_VALLEY: usize = 200;
const MIN_DEPTH: u32 = 20;

/// A narrow, deep read-support valley between two long dense regions is an
/// assembler join that no original fragment substantiates: each side has
/// independent evidence, but the molecule connecting them does not. Report
/// the valley's k-mer span so both flanks can be presented separately rather
/// than as one false bridge or as a single clipped island. Depth is derived
/// only from the original pairs; no reference or truth enters this decision.
pub(in super::super) fn junction(depth: &[u32]) -> Option<(usize, usize)> {
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
        if i - start <= MAX_VALLEY
            && start >= MIN_FLANK
            && depth.len() - i >= MIN_FLANK
            && core <= low
            && dense(&depth[..start], high)
            && dense(&depth[i..], high)
            && best.is_none_or(|(_, _, seen)| core < seen)
        {
            best = Some((start, i, core));
        }
    }
    best.map(|(a, b, _)| (a, b))
}

/// Render intervals in contig coordinates; without a deep valley this is the
/// single whole contig and the established presentation path is unchanged.
pub(in super::super) fn pieces(depth: &[u32], length: usize) -> Vec<(usize, usize)> {
    junction(depth).map_or_else(
        || vec![(0, length)],
        |(a, b)| vec![(0, (a + K).min(length)), (b, length)],
    )
}

fn dense(depth: &[u32], high: u32) -> bool {
    depth.iter().filter(|&&v| v >= high).count() * 100 >= depth.len() * 90
}
