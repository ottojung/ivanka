use std::collections::HashMap;
use super::index::{build_prep, unique_flanks, ReadPrep};
use super::place::original_pair_calls_cached_borrowed;

pub(super) struct PrepCache {
    pub preps: Vec<ReadPrep>,
}

pub(super) fn make_prep(reads: &[Vec<u8>], qualities: &[Vec<u8>], a: usize) -> PrepCache {
    PrepCache { preps: build_prep(reads, qualities, a) }
}

pub(super) fn observations_cached(seq: &[u8], reads: &[Vec<u8>], cache: &PrepCache, a: usize) -> Vec<HashMap<usize, u8>> {
    if cache.preps.len() != reads.len() {
        return Vec::new();
    }
    let index = unique_flanks(seq, a);
    let mut out = Vec::with_capacity(reads.len() / 4);
    let mut i = 0;
    while i + 4 <= reads.len() {
        let pr = [&reads[i], &reads[i + 1], &reads[i + 2], &reads[i + 3]];
        let pp = [&cache.preps[i], &cache.preps[i + 1], &cache.preps[i + 2], &cache.preps[i + 3]];
        out.push(original_pair_calls_cached_borrowed(&pr, &pp, &index, a));
        i += 4;
    }
    out
}

#[cfg(test)]
pub(super) fn observations(seq: &[u8], reads: &[Vec<u8>], qualities: &[Vec<u8>], a: usize) -> Vec<HashMap<usize, u8>> {
    let cache = make_prep(reads, qualities, a);
    observations_cached(seq, reads, &cache, a)
}
