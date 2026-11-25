use super::canonical_kmer;
use std::collections::HashMap;

pub(super) fn path(seed: u64, len: usize) -> Vec<u8> {
    let mut x = seed;
    (0..len)
        .map(|_| {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            b"ACGT"[(x & 3) as usize]
        })
        .collect()
}

pub(super) fn sampled(seq: &[u8]) -> HashMap<u64, u32> {
    seq.windows(31)
        .filter_map(canonical_kmer)
        .map(|k| (k, 10))
        .collect()
}

pub(super) fn fasta_seqs(text: &str) -> Vec<Vec<u8>> {
    let mut out = Vec::new();
    for line in text.lines() {
        if line.starts_with('>') {
            out.push(Vec::new());
        } else if let Some(last) = out.last_mut() {
            last.extend_from_slice(line.as_bytes());
        }
    }
    out
}
