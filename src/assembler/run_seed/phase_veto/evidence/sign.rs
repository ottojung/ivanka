use super::encode::encode_a;
use super::{FlankIndex, A, K128};
use std::collections::HashMap;

// Distinct original R1/R2 sequence signatures are identified once, not per
// candidate. Group indices identify physical read-pair observations; equal
// sequences share an id so they cannot inflate the distinct-signature count.
pub(crate) fn signature_ids(reads: &[Vec<u8>]) -> Vec<u32> {
    let mut map: HashMap<(&[u8], &[u8]), u32> = HashMap::new();
    reads
        .chunks_exact(4)
        .map(|g| {
            let next = map.len() as u32 + 1;
            *map.entry((g[0].as_slice(), g[2].as_slice()))
                .or_insert(next)
        })
        .collect()
}

pub(crate) fn uniq_flanks(seq: &[u8]) -> FlankIndex {
    let mut out = FlankIndex::default();
    for (i, w) in seq.windows(2 * A + 1).enumerate() {
        if w[A] == b'N' {
            continue;
        }
        let (Some(l), Some(r)) = (encode_a(&w[..A]), encode_a(&w[A + 1..])) else {
            continue;
        };
        let key = ((l as K128) << (2 * A)) | (r as K128);
        out.entry(key)
            .and_modify(|v| {
                if *v != Some(i + A) {
                    *v = None;
                }
            })
            .or_insert(Some(i + A));
    }
    out
}
