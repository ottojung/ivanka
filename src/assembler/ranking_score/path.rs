//! Read-supported phased alternatives beyond a single substitution.
use std::collections::{HashMap, HashSet};

const K: usize = 31;
const MIN_RUN: usize = 8;
const MIN_PHASED: usize = 16;
const MIN_SUPPORT: usize = 50;

// A candidate can share almost every 31-mer with a retained contig and still
// carry distinct internally clustered paths supported by the original reads.
// Sampled windows are three bases apart: one substitution leaves one short
// run, so a long run or two separated runs are required. End-local runs are
// extension tails, not independent paths. Truth never enters this decision.
pub(crate) fn supported_path_alternative(
    seq: &[u8],
    support: usize,
    represented: &HashSet<u64>,
    sampled: &HashMap<u64, u32>,
    canonical: fn(&[u8]) -> Option<u64>,
) -> bool {
    if support < MIN_SUPPORT || seq.len() < 4 * K || sampled.is_empty() {
        return false;
    }
    let mut runs = Vec::new();
    let (mut run, mut start, mut last) = (0usize, 0usize, None);
    for (i, key) in seq
        .windows(K)
        .enumerate()
        .filter_map(|(i, w)| canonical(w).map(|k| (i, k)))
    {
        if !i.is_multiple_of(3)
            || represented.contains(&key)
            || sampled.get(&key).copied().unwrap_or(0) < 5
        {
            continue;
        }
        if let Some(p) = last {
            if i - p > 3 {
                runs.push((run, start, p));
                run = 0;
            }
        }
        if run == 0 {
            start = i;
        }
        run += 1;
        last = Some(i);
    }
    runs.push((run, start, last.unwrap_or(0)));
    let internal = |x: &(usize, usize, usize)| x.1 >= K && x.2 + K + K <= seq.len();
    runs.iter()
        .filter(|x| x.0 >= MIN_RUN && internal(x))
        .count()
        >= 2
        || runs.iter().any(|x| x.0 >= MIN_PHASED && internal(x))
}

#[cfg(test)]
mod tests;
