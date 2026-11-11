use super::redundancy;
use super::{ranked_candidates, HashMap, HashSet};
/// Prioritize read evidence and k-mer novelty with a protected seed prefix.
/// Redundant local SNV alternatives are withheld from the ordinary contigs
/// and may be reported separately as explicitly unphased observations.
pub(crate) fn select_supported_contigs_with_kmers(
    seqs: Vec<Vec<u8>>,
    counts: Vec<usize>,
    n: usize,
    protected: usize,
    sampled: &HashMap<u64, u32>,
) -> super::ContigSelection {
    let candidates = ranked_candidates(seqs, counts, n, protected);
    // Use read support to prioritize assemblies and k-mer novelty to avoid
    // passing hundreds of near-identical contigs into MiCall's stitcher.
    let mut retained = Vec::new();
    let mut retained_support = Vec::new();
    let mut variants = Vec::new();
    let mut represented = HashSet::new();
    let mut duplicates = 0usize;
    let mut no_extension_support = 0usize;
    for (index, (seq, support)) in candidates {
        if retained.len() >= n {
            break;
        }
        let is_seed = index < protected;
        if !is_seed && support == 0 {
            no_extension_support += 1;
            continue;
        }
        let (valid, shared, short_shadow, snv) = super::evaluation::evaluate(
            &seq,
            support,
            &represented,
            &retained,
            &retained_support,
            sampled,
        );
        if !is_seed && valid > 0 && (shared * 20 >= valid * 19 || short_shadow) {
            super::report::duplicate(snv, seq, support, &mut variants, &mut duplicates);
            continue;
        }
        redundancy::represent(&seq, &mut represented);
        retained.push(seq);
        retained_support.push(support);
    }
    super::report::finish(retained, variants, duplicates, no_extension_support)
}
