use super::K;
use std::collections::HashMap;
pub(super) type ByteHits = HashMap<[u8; K], Vec<(usize, usize)>>;

fn rc(key: &[u8; K]) -> [u8; K] {
    let mut out = [0u8; K];
    for (i, &base) in key.iter().rev().enumerate() {
        out[i] = match base {
            b'A' => b'T',
            b'C' => b'G',
            b'G' => b'C',
            _ => b'A',
        };
    }
    out
}

/// Original byte-key index, reproduced verbatim for differential testing.
pub(super) fn build(contigs: &[Vec<u8>]) -> ByteHits {
    let mut index = ByteHits::new();
    for (candidate, sequence) in contigs.iter().enumerate() {
        for (position, window) in sequence.windows(K).enumerate() {
            if !window
                .iter()
                .all(|base| matches!(base, b'A' | b'C' | b'G' | b'T'))
            {
                continue;
            }
            let key: [u8; K] = window.try_into().expect("fixed-length window");
            index.entry(key).or_default().push((candidate, position));
            index
                .entry(rc(&key))
                .or_default()
                .push((candidate, position));
        }
    }
    index.retain(|_, loci| loci.len() <= 8);
    index
}
