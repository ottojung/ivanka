//! Canonical short seeds for orientation-independent self-similarity.

use std::collections::HashSet;

const SEED: usize = 12;

/// Encode a DNA word as the smaller of its forward and reverse-complement
/// two-bit codes. Ambiguous bases yield no seed rather than a guessed code.
fn canonical(word: &[u8]) -> Option<u64> {
    let mut forward = 0u64;
    let mut reverse = 0u64;
    for (position, &base) in word.iter().enumerate() {
        let code: u64 = match base {
            b'A' => 0,
            b'C' => 1,
            b'G' => 2,
            b'T' => 3,
            _ => return None,
        };
        forward |= code << (2 * position);
        reverse |= (3 - code) << (2 * (SEED - 1 - position));
    }
    Some(forward.min(reverse))
}

/// Seeds of one half-open window; ambiguous words are simply absent.
pub(super) fn window(sequence: &[u8], start: usize, end: usize) -> HashSet<u64> {
    (start..=end - SEED)
        .filter_map(|at| canonical(&sequence[at..at + SEED]))
        .collect()
}
