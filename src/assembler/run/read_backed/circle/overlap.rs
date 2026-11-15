/// A closed path repeats an exact suffix at its beginning.
pub(super) fn length(sequence: &[u8], min: usize, max: usize) -> Option<usize> {
    (min..=max.min(sequence.len() / 2))
        .rev()
        .find(|&n| sequence[..n] == sequence[sequence.len() - n..])
}

/// Split a divergent copied tail rather than assert unobserved long-range phase.
pub(super) fn divergent_tail_cut(
    sequence: &[u8],
    depth: &[u32],
    k: usize,
    min_tail: usize,
) -> Option<usize> {
    const ANCHOR: usize = 256;
    if sequence.len() < 2 * min_tail || depth.len() != sequence.len() - k + 1 {
        return None;
    }
    let prefix = &sequence[..ANCHOR];
    let suffix = &sequence[sequence.len() - ANCHOR..];
    let mut chosen = None;
    for (start, window) in sequence.windows(ANCHOR).enumerate() {
        // Reordering a circular or branched path can move the same anchor.
        let cut = if window == prefix {
            start
        } else if window == suffix {
            sequence.len() - ANCHOR - start
        } else {
            continue;
        };
        let tail = sequence.len() - cut;
        if tail < min_tail || tail >= cut {
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
