use super::{index, island, ranking, scoring, tiling, trimming, Reads, K};
mod legacy_equivalence;
mod mate_cases;
mod mate_controls;
mod ranking_cases;
mod tiling_cases;
mod trimming_cases;

/// Deterministic nonrepetitive fixture bases; no reference or truth input.
fn sequence(seed: u64, len: usize) -> Vec<u8> {
    let mut state = seed;
    (0..len)
        .map(|_| {
            state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
            b"ACGT"[(state >> 33) as usize & 3]
        })
        .collect()
}

fn reverse_complement(seq: &[u8]) -> Vec<u8> {
    seq.iter()
        .rev()
        .map(|base| match base {
            b'A' => b'T',
            b'C' => b'G',
            b'G' => b'C',
            _ => b'A',
        })
        .collect()
}

/// Each original pair contributes four oriented entries in index order.
fn paired(mates: &[(Vec<u8>, Vec<u8>)]) -> Reads {
    let mut seqs = Vec::new();
    for (a, b) in mates {
        seqs.extend([
            a.clone(),
            reverse_complement(a),
            b.clone(),
            reverse_complement(b),
        ]);
    }
    Reads {
        seqs,
        index: Default::default(),
        seed_counts: Default::default(),
        max_read_len: 0,
        overlength_rejections: Default::default(),
        overhang_cache: Default::default(),
    }
}
