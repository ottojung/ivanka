use super::trimming;

/// Retain the densest major evidence island only when clipping is justified.
pub(super) fn bounds(sequence: &[u8], depth: &[u32]) -> (usize, usize) {
    let terminal = trimming::bounds(sequence, depth);
    if terminal != (0, sequence.len()) {
        return terminal;
    }
    let good = depth
        .iter()
        .enumerate()
        .filter(|(_, v)| **v >= 3)
        .map(|(i, _)| i)
        .collect::<Vec<_>>();
    if good.len() < 500 {
        return terminal;
    }
    let mut islands = Vec::new();
    let (mut first, mut last, mut count, mut support) = (good[0], good[0], 0, 0u64);
    for position in good {
        if position - last > 200 {
            islands.push((first, last, count, support));
            first = position;
            count = 0;
            support = 0;
        }
        last = position;
        count += 1;
        support += u64::from(depth[position]);
    }
    islands.push((first, last, count, support));
    let best = islands
        .into_iter()
        .filter(|&(a, b, n, _)| n >= 500 && n * 100 >= 85 * (b - a + 1))
        .max_by_key(|&(a, _, n, support)| (n, support, std::cmp::Reverse(a)));
    best.map(|(a, b, _, _)| trimming::clip(sequence.len(), a, b))
        .unwrap_or(terminal)
}
