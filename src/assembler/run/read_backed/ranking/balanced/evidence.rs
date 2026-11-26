use super::{Statistics, K};
use std::collections::HashSet;

/// Private windows, longest supported run, count of long runs, median depth
/// and the window bounds of the longest run. Only reads and already chosen
/// contigs are consulted; no reference or truth is used.
pub(super) fn scan(
    contigs: &[Vec<u8>],
    stats: &Statistics,
    selected: u16,
    candidate: usize,
    min_run: usize,
) -> (usize, usize, usize, u32, (usize, usize)) {
    let mut retained = HashSet::new();
    for (i, seq) in contigs.iter().enumerate() {
        if selected & (1 << i) != 0 {
            for window in seq.windows(K) {
                retained.insert(window.to_vec());
            }
        }
    }
    let mut depths = Vec::new();
    let (mut run, mut longest, mut islands, mut count) = (0usize, 0usize, 0usize, 0usize);
    let (mut begin, mut bounds) = (0usize, (0usize, 0usize));
    for (j, window) in contigs[candidate].windows(K).enumerate() {
        if !retained.contains(window) {
            count += 1;
            if stats.depth[candidate][j] >= 3 {
                if run == 0 {
                    begin = j;
                }
                run += 1;
                if run > longest {
                    longest = run;
                    bounds = (begin, j);
                }
                depths.push(stats.depth[candidate][j]);
                continue;
            }
        }
        if run >= min_run {
            islands += 1;
        }
        run = 0;
    }
    if run >= min_run {
        islands += 1;
    }
    depths.sort_unstable();
    let median = depths.get(depths.len() / 2).copied().unwrap_or(0);
    (count, longest, islands, median, bounds)
}
