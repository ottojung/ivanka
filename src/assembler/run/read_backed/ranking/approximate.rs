//! Conservative approximate-repeat join detection from read-derived evidence.
//!
//! Similarity alone cannot separate a spurious second traversal from a real
//! homologous repeat. A split is proposed only when two disjoint windows share
//! read-supported seeds AND original pairs stop spanning the transition.
//! No truth, reference, family label or fitted genome length is used.

use super::spans;

const WINDOW: usize = 2000;
const STEP: usize = 1000;
const MIN_SHARED: u32 = 250;
const MIN_DEPTH: u32 = 3;

pub(crate) fn junction(
    seq: &[u8],
    depth: &[u32],
    pairs: &[(usize, usize)],
) -> Option<(usize, usize)> {
    if seq.len() < 2 * WINDOW + spans::SEED {
        return None;
    }
    let starts: Vec<usize> = (0..=seq.len() - WINDOW).step_by(STEP).collect();
    let sets: Vec<_> = starts
        .iter()
        .map(|&start| spans::supported_seeds(seq, depth, start, WINDOW))
        .collect();
    for i in 0..sets.len() {
        for j in i + 1..sets.len() {
            if starts[j] < starts[i] + WINDOW + spans::SEED {
                continue;
            }
            let smaller = sets[i].len().min(sets[j].len()).max(1) as u32;
            let shared = sets[i].intersection(&sets[j]).count() as u32 * 1000 / smaller;
            if shared < MIN_SHARED {
                continue;
            }
            let (a, b) = (starts[i] + WINDOW, starts[j]);
            if spans::unsupported(pairs, a, b)
                && spans::dense(&depth[..a.min(depth.len())], MIN_DEPTH)
                && spans::dense(&depth[b.min(depth.len())..], MIN_DEPTH)
            {
                return Some((a, b));
            }
        }
    }
    None
}
