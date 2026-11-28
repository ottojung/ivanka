//! Detect a contig that traverses one path more than once, using only its own
//! sequence. No reference, truth, family label or score reaches this module.

use super::seed;

const WINDOW: usize = 2000;
const STRIDE: usize = 1000;
const MIN_SHARED_PER_MILLE: u32 = 250;

/// Seed sharing (per mille) and the two disjoint window starts of the
/// strongest repeated pair. Disjoint windows stop a single local repeat from
/// matching itself; short seeds tolerate the divergence between two strains.
pub(in crate::assembler::run::read_backed) fn repeated_path(
    sequence: &[u8],
) -> Option<(u32, usize, usize)> {
    if sequence.len() < 2 * WINDOW {
        return None;
    }
    let starts: Vec<usize> = (0..=sequence.len() - WINDOW).step_by(STRIDE).collect();
    let sets: Vec<_> = starts
        .iter()
        .map(|&start| seed::window(sequence, start, start + WINDOW))
        .collect();
    let (mut best_score, mut best_pair) = (0u32, (0usize, 0usize));
    for i in 0..sets.len() {
        for j in i + 1..sets.len() {
            if starts[j] < starts[i] + WINDOW {
                continue;
            }
            let smallest = sets[i].len().min(sets[j].len()).max(1) as u32;
            let shared = sets[i].intersection(&sets[j]).count() as u32 * 1000 / smallest;
            if shared > best_score {
                best_score = shared;
                best_pair = (starts[i], starts[j]);
            }
        }
    }
    (best_score >= MIN_SHARED_PER_MILLE).then_some((best_score, best_pair.0, best_pair.1))
}
