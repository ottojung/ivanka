use super::detect;
use super::Evidence;
use std::collections::hash_map::Entry;
use std::collections::HashMap;

// The veto verdict is a pure function of (candidate sequence, original read
// pairs). Evaluate each distinct eligible candidate once, split into bounded
// scoped-thread chunks; no reference, panel or score is read. Results are
// written back in input order so downstream selection stays byte-identical.
pub(super) fn evaluate(ev: &Evidence, seqs: &[Vec<u8>], reads: &[Vec<u8>], protected: usize) -> Vec<bool> {
    let n = seqs.len();
    let mut verdict = vec![false; n];
    let mut first: Vec<usize> = (0..n).collect();
    let mut fresh = Vec::new();
    let mut seen = HashMap::<&[u8], usize>::new();
    for (i, seq) in seqs.iter().enumerate() {
        if seq.len() < 200 || i < protected { continue; }
        match seen.entry(seq.as_slice()) {
            Entry::Occupied(e) => first[i] = *e.get(),
            Entry::Vacant(e) => { e.insert(i); fresh.push(i); }
        }
    }
    let mut results = vec![false; fresh.len()];
    let threads = std::thread::available_parallelism().map(|x| x.get()).unwrap_or(1).min(8);
    let chunk = fresh.len().div_ceil(threads).max(1);
    std::thread::scope(|scope| {
        for (idxs, out) in fresh.chunks(chunk).zip(results.chunks_mut(chunk)) {
            scope.spawn(move || {
                for (k, &i) in idxs.iter().enumerate() {
                    out[k] = detect::incompatible(&seqs[i], reads, &ev.preps, &ev.sigs);
                }
            });
        }
    });
    for (k, &i) in fresh.iter().enumerate() { verdict[i] = results[k]; }
    for i in 0..n { if first[i] != i { verdict[i] = verdict[first[i]]; } }
    verdict
}
