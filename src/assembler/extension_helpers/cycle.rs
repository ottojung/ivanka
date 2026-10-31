use std::collections::{HashMap, HashSet};

pub(crate) const CYCLE_MATCH: usize = 512;
const CYCLE_MIN_SPACING: usize = 2000;

pub(crate) fn cycle_end(seq: &[u8], k: usize, encode: fn(&[u8])->Option<u64>) -> Option<usize> {
    if seq.len() < CYCLE_MIN_SPACING + CYCLE_MATCH { return None; }
    let mut first = HashMap::<u64, usize>::new();
    for i in 0..=seq.len() - CYCLE_MATCH {
        let Some(anchor) = encode(&seq[i..i + k]) else { continue;
        };
        if let Some(&j) = first.get(&anchor) {
            if i - j >= CYCLE_MIN_SPACING
                && seq[j..j + CYCLE_MATCH] == seq[i..i + CYCLE_MATCH]
                && seq[j..j + CYCLE_MATCH]
                    .windows(k).step_by(32)
                    .filter_map(encode).collect::<HashSet<_>>().len() >= 8 {
                return Some(i + CYCLE_MATCH);
            }
        } else {
            first.insert(anchor, i);
        }
    }
    None
}
