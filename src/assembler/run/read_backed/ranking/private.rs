use super::K;
use std::collections::HashSet;

// Positions whose oriented 31-mer is absent from every retained component.
// Only original reads and already chosen candidates are consulted; a shared
// fragment cannot masquerade as distinct evidence.
pub(super) fn positions(contigs: &[Vec<u8>], selected: &[usize], candidate: usize) -> usize {
    let mut retained = HashSet::<[u8; K]>::new();
    for &index in selected {
        for window in contigs[index].windows(K) {
            if let Ok(key) = <[u8; K]>::try_from(window) {
                retained.insert(key);
                retained.insert(reverse(window));
            }
        }
    }
    contigs[candidate]
        .windows(K)
        .filter(|window| {
            let Ok(key) = <[u8; K]>::try_from(*window) else {
                return false;
            };
            !retained.contains(&key) && !retained.contains(&reverse(window))
        })
        .count()
}

fn reverse(window: &[u8]) -> [u8; K] {
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
