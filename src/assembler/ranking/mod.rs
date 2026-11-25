use super::ranking_score::{ranked_candidates, supported_snv_alternative};
use super::reads::{encode, rolling_canonical_kmers, K};
use std::collections::{HashMap, HashSet};
mod evaluation;
mod kmer;
mod redundancy;
mod report;
mod selection;
pub(super) type ContigSelection = (Vec<Vec<u8>>, Vec<(Vec<u8>, usize)>);
pub(super) use kmer::canonical_kmer;
pub(super) use selection::select_supported_contigs_with_kmers;
// Test-only convenience for redundancy rules that need no read evidence.
// Production never uses an empty sampled map: without read k-mers a suppressed
// Hamming-1 neighbour has no audit channel and a true haplotype would be lost.
#[cfg(test)]
pub(super) fn select_supported_contigs(
    seqs: Vec<Vec<u8>>,
    counts: Vec<usize>,
    n: usize,
    protected: usize,
) -> Vec<Vec<u8>> {
    select_supported_contigs_with_kmers(seqs, counts, n, protected, &HashMap::new()).0
}
