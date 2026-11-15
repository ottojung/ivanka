/// A closed path repeats an exact suffix at its beginning.
pub(super) fn length(sequence: &[u8], min: usize, max: usize) -> Option<usize> {
    (min..=max.min(sequence.len() / 2))
        .rev()
        .find(|&n| sequence[..n] == sequence[sequence.len() - n..])
}

/// Split a divergent copied tail rather than assert unobserved long-range phase.
pub(super) fn alternative_tail_cut(sequence: &[u8], depth: &[u32], k: usize) -> Option<usize> {
    const ANCHOR: usize = 256;
    const MIN_TAIL: usize = 2000;
    if sequence.len() < 2 * MIN_TAIL || depth.len() != sequence.len() - k + 1 {
        return None;
    }
    let suffix = &sequence[sequence.len() - ANCHOR..];
    let mut chosen = None;
    for (start, window) in sequence[..sequence.len() - ANCHOR]
        .windows(ANCHOR)
        .enumerate()
    {
        if window != suffix {
            continue;
        }
        let cut = sequence.len() - ANCHOR - start;
        let tail = sequence.len() - cut;
        if tail < MIN_TAIL || tail >= cut {
            continue;
        }
        let matched = sequence[..tail]
            .iter()
            .zip(&sequence[cut..])
            .filter(|(a, b)| a == b)
            .count();
        if matched * 100 < 80 * tail || matched * 100 >= 99 * tail {
            continue;
        }
        let well_covered = |region: &[u32]| {
            !region.is_empty() && region.iter().filter(|&&n| n >= 3).count() * 5 >= 4 * region.len()
        };
        if !well_covered(&depth[..cut - k + 1]) || !well_covered(&depth[cut..]) {
            continue;
        }
        if chosen.replace(cut).is_some() {
            return None;
        }
    }
    chosen
}
