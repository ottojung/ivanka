use super::{next_anchor, repeats, CYCLE_MATCH, CYCLE_MIN_SPACING};
use std::collections::HashMap;
pub(crate) fn cycle_end(seq: &[u8], k: usize, encode: fn(&[u8]) -> Option<u64>) -> Option<usize> {
    if seq.len() < CYCLE_MIN_SPACING + CYCLE_MATCH {
        return None;
    }
    let mut first = HashMap::<u64, usize>::new();
    let mut previous = None;
    for i in 0..=seq.len() - CYCLE_MATCH {
        let anchor = next_anchor(seq, i, k, previous, encode);
        previous = anchor;
        let Some(anchor) = anchor else {
            continue;
        };
        if let Some(&j) = first.get(&anchor) {
            if repeats(seq, j, i, k, encode) {
                return Some(i + CYCLE_MATCH);
            }
        } else {
            first.insert(anchor, i);
        }
    }
    None
}
