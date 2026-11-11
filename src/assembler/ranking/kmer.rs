use super::{encode, K};
pub(crate) fn canonical_kmer(seq: &[u8]) -> Option<u64> {
    let f = encode(seq)?;
    let mut r = 0u64;
    for i in 0..K {
        r = (r << 2) | (3 - ((f >> (2 * i)) & 3));
    }
    Some(f.min(r))
}
