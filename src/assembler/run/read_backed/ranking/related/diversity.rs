use super::{Statistics, K};
use std::collections::HashSet;

pub(super) fn diversity(stats: &Statistics, selected: u16, i: usize) -> (usize, usize) {
    let mut signatures = HashSet::new();
    let mut ranges = Vec::new();
    for &(pair, min, max) in &stats.exclusive_ranges[i] {
        let pair = pair as usize;
        if stats.exclusive_masks.get(pair).copied().unwrap_or(0) & selected != 0 {
            continue;
        }
        signatures.insert(stats.pair_signatures[pair]);
        ranges.push((min, max));
    }
    ranges.sort_unstable();
    let mut clusters = 0usize;
    let mut end = 0u32;
    for (min, max) in ranges {
        if clusters == 0 || min >= end {
            clusters += 1;
            end = max + K as u32;
        } else {
            end = end.max(max + K as u32);
        }
    }
    (signatures.len(), clusters)
}
