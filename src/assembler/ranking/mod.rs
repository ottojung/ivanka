use super::ranking_score::{ranked_candidates, supported_snv_alternative};
use super::reads::{encode, rolling_canonical_kmers, K};
use std::collections::{HashMap, HashSet};
mod evaluation;
mod kmer;
mod read_support;
mod redundancy;
mod report;
mod selection;
#[cfg(test)]
mod tests;
pub(super) type ContigSelection = (Vec<Vec<u8>>, Vec<(Vec<u8>, usize)>);
pub(super) use kmer::canonical_kmer;
pub(super) use selection::select_supported_contigs_with_kmers;
#[cfg(test)]
pub(super) fn select_supported_contigs(
    seqs: Vec<Vec<u8>>,
    counts: Vec<usize>,
    n: usize,
    protected: usize,
) -> Vec<Vec<u8>> {
    select_supported_contigs_with_kmers(seqs, counts, n, protected, &HashMap::new()).0
}

/// Reference-blind admission: original-read full-span support decides whether
/// weakly-supported variants are withheld from the ordinary FASTA.
pub(super) fn select_supported_contigs_read_support(
    seqs: Vec<Vec<u8>>,
    counts: Vec<usize>,
    n: usize,
    protected: usize,
    sampled: &HashMap<u64, u32>,
) -> Vec<Vec<u8>> {
    // Preserve the parent's native selection exactly: read-derived k-mer
    // novelty is used by the audit path only, never to admit ordinary contigs.
    let retained =
        select_supported_contigs_with_kmers(seqs, counts, n, protected, &HashMap::new()).0;
    read_support::admit(retained, protected, sampled)
}
