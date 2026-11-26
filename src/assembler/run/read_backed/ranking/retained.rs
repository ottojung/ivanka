use super::K;
use std::collections::HashSet;

pub(super) type Keys = HashSet<[u8; K]>;

// One orientation-independent set per selection round. Rebuilding it for each
// candidate made private scoring quadratic in the candidate count.
pub(super) fn keys(contigs: &[Vec<u8>], selected: &[usize]) -> Keys {
    let mut keys = HashSet::new();
    for &index in selected {
        for window in contigs[index].windows(K) {
            if let Ok(key) = <[u8; K]>::try_from(window) {
                keys.insert(key);
                keys.insert(reverse(window));
            }
        }
    }
    keys
}

pub(super) fn reverse(window: &[u8]) -> [u8; K] {
    let mut key = [0u8; K];
    for (target, base) in key.iter_mut().zip(window.iter().rev()) {
        *target = match base {
            b'A' => b'T',
            b'C' => b'G',
            b'G' => b'C',
            _ => b'A',
        };
    }
    key
}
