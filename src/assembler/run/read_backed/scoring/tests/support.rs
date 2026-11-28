//! Read-derived fixture helpers. Candidate sequences are synthetic ACGT only;
//! no reference, panel or evaluator score is involved.

use super::Reads;

pub(super) fn rc(seq: &[u8]) -> Vec<u8> {
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

pub(super) fn sequence(len: usize, seed: u64) -> Vec<u8> {
    let mut state = seed;
    (0..len)
        .map(|_| {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            b"ACGT"[(state & 3) as usize]
        })
        .collect()
}

pub(super) fn reads(pairs: &[(Vec<u8>, Vec<u8>)]) -> Reads {
    let mut seqs = Vec::new();
    for (first, second) in pairs {
        seqs.extend([first.clone(), rc(first), second.clone(), rc(second)]);
    }
    Reads {
        seqs,
        index: Default::default(),
        seed_counts: Default::default(),
        max_read_len: 128,
        overlength_rejections: Default::default(),
        overhang_cache: Default::default(),
    }
}

pub(super) fn tiled(seq: &[u8], len: usize) -> Vec<(Vec<u8>, Vec<u8>)> {
    (0..=seq.len() - len)
        .map(|start| {
            let mate = (start + len / 2).min(seq.len() - len);
            (seq[start..start + len].to_vec(), rc(&seq[mate..mate + len]))
        })
        .collect()
}
