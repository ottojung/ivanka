use super::K;

/// Preserve 512 bases around the broadest terminal supported interval.
pub(super) fn bounds(sequence: &[u8], depth: &[u32]) -> (usize, usize) {
    let unchanged = (0, sequence.len());
    let good = depth
        .iter()
        .enumerate()
        .filter(|(_, v)| **v >= 3)
        .map(|(i, _)| i)
        .collect::<Vec<_>>();
    if good.len() < 500 {
        return unchanged;
    }
    let (first, last) = (good[0], *good.last().unwrap());
    if good.len() * 100 < 85 * (last - first + 1) {
        return unchanged;
    }
    clip(sequence.len(), first, last)
}

pub(super) fn clip(length: usize, first: usize, last: usize) -> (usize, usize) {
    let left = if first >= 1024 {
        first.saturating_sub(512)
    } else {
        0
    };
    let covered_end = last + K;
    let right = if length.saturating_sub(covered_end) >= 1024 {
        (covered_end + 512).min(length)
    } else {
        length
    };
    if left >= right {
        (0, length)
    } else {
        (left, right)
    }
}
