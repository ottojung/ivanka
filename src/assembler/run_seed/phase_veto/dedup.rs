use std::collections::hash_map::Entry;
use std::collections::HashMap;

// Deduplicate by borrowed sequence slice (never clone a candidate into a
// cache key). Returns the verdict slots, each eligible index's representative,
// and the distinct candidate indices that need a real scan.
pub(super) fn plan(seqs: &[Vec<u8>], protected: usize) -> (Vec<bool>, Vec<usize>, Vec<usize>) {
    let n = seqs.len();
    let verdict = vec![false; n];
    let mut first: Vec<usize> = (0..n).collect();
    let mut fresh = Vec::new();
    let mut seen = HashMap::<&[u8], usize>::new();
    for (i, seq) in seqs.iter().enumerate() {
        if seq.len() < 200 || i < protected {
            continue;
        }
        match seen.entry(seq.as_slice()) {
            Entry::Occupied(e) => first[i] = *e.get(),
            Entry::Vacant(e) => {
                e.insert(i);
                fresh.push(i);
            }
        }
    }
    (verdict, first, fresh)
}

pub(super) fn propagate(verdict: &mut [bool], first: &[usize], fresh: &[usize], results: &[bool]) {
    for (k, &i) in fresh.iter().enumerate() {
        verdict[i] = results[k];
    }
    for i in 0..verdict.len() {
        if first[i] != i {
            verdict[i] = verdict[first[i]];
        }
    }
}
