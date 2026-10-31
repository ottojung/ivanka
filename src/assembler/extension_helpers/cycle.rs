use std::collections::{HashMap, HashSet};

pub(crate) const CYCLE_MATCH: usize = 512;
// The 31-mer index uses two bits per base. Advance an encoded window in O(1)
// when possible; ambiguous bases fall back to the original exact encoder.
pub(super) fn next_anchor(seq: &[u8], i: usize, k: usize, previous: Option<u64>,
                          encode: fn(&[u8])->Option<u64>) -> Option<u64> {
    if k == 31 && i > 0 {
        if let Some(prev) = previous {
            let digit = match seq[i + k - 1] {
                b'A' => Some(0), b'C' => Some(1), b'G' => Some(2), b'T' => Some(3),
                _ => None
            };
            if let Some(d) = digit { return Some(((prev << 2) & ((1u64 << 62)-1)) | d); }
        }
    }
    encode(&seq[i..i+k])
}
pub(super) const CYCLE_MIN_SPACING: usize = 2000;

pub(super) fn repeats(seq:&[u8],j:usize,i:usize,k:usize,encode:fn(&[u8])->Option<u64>)->bool {
    i-j>=CYCLE_MIN_SPACING && seq[j..j+CYCLE_MATCH]==seq[i..i+CYCLE_MATCH]
        && seq[j..j+CYCLE_MATCH].windows(k).step_by(32)
            .filter_map(encode).collect::<HashSet<_>>().len()>=8
}
pub(crate) fn cycle_end(seq: &[u8], k: usize, encode: fn(&[u8])->Option<u64>) -> Option<usize> {
    if seq.len() < CYCLE_MIN_SPACING + CYCLE_MATCH { return None; }
    let mut first = HashMap::<u64, usize>::new();
    let mut previous = None;
    for i in 0..=seq.len() - CYCLE_MATCH {
        let anchor = next_anchor(seq, i, k, previous, encode);
        previous = anchor;
        let Some(anchor) = anchor else { continue;
        };
        if let Some(&j) = first.get(&anchor) {
            if repeats(seq,j,i,k,encode) {return Some(i+CYCLE_MATCH);}
        } else {
            first.insert(anchor, i);
        }
    }
    None
}
