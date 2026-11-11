use super::{canonical_kmer, rolling_canonical_kmers, supported_snv_alternative, HashSet};
pub(super) fn overlap(
    seq: &[u8],
    represented: &HashSet<u64>,
    retained: &[Vec<u8>],
) -> (usize, usize, bool) {
    let mut valid = 0usize;
    let mut shared = 0usize;
    for k in rolling_canonical_kmers(&seq) {
        valid += 1;
        if represented.contains(&k) {
            shared += 1;
        }
    }
    // A short sequence nearly contained in a longer supported contig adds
    // little assembly coverage but can divert reads during MiCall remapping.
    // Use a less strict overlap threshold only for these short fragments;
    // equal-length alternatives retain the normal haplotype-diversity rule.
    let longest = retained.iter().map(Vec::len).max().unwrap_or(0);
    let short_shadow = seq.len() * 4 <= longest * 3 && shared * 20 >= valid * 17;
    (valid, shared, short_shadow)
}

// A one-base difference is retained separately only with enough read evidence.
pub(super) fn is_supported_alternative(
    seq: &[u8],
    support: usize,
    retained: &[Vec<u8>],
    retained_support: &[usize],
    sampled: &super::HashMap<u64, u32>,
) -> bool {
    supported_snv_alternative(
        &seq,
        support,
        retained,
        retained_support,
        sampled,
        canonical_kmer,
    )
}

// Canonical windows are an orientation-independent redundancy summary.
pub(super) fn represent(seq: &[u8], represented: &mut HashSet<u64>) {
    for k in rolling_canonical_kmers(seq) {
        represented.insert(k);
    }
}
