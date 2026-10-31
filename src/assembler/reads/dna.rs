

pub(crate) const K: usize = 31;
pub(crate) const INDEX_STEP: usize = 12;
pub(crate) const MAX_EXTENSION: usize = 100;
pub(crate) const MAX_CONTIG_LENGTH: usize = 25000;

pub(crate) fn rc(seq: &[u8]) -> Vec<u8> {
    seq.iter().rev().map(|b| match b { b'A' => b'T', b'C' => b'G', b'G' => b'C',
        b'T' => b'A', _ => b'N' }).collect()
}
pub(crate) fn encode(seq: &[u8]) -> Option<u64> {
    if seq.len() != K { return None; }
    let mut n = 0u64;
    for b in seq {
        let d = match b { b'A'=>0, b'C'=>1, b'G'=>2, b'T'=>3, _=>return None };
        n = (n << 2) | d;
    }
    Some(n)
}
pub(crate) fn decode(mut val: u64) -> Vec<u8> {
    let mut out = vec![0; K];
    for x in out.iter_mut().rev() {
        *x = match val & 3 { 0=>b'A',1=>b'C',2=>b'G',_=>b'T' };
        val >>= 2;
    }
    out
}
