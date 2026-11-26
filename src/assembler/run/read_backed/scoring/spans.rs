/// One original pair contributes its extreme mapped loci on a candidate.
/// The accumulator deduplicates loci before this call, so a slice has the
/// same unique-locus set as the reference HashSet formulation.
pub(in super::super) fn extremes(loci: &[usize]) -> (usize, usize) {
    (
        *loci.iter().min().expect("nonempty supported loci"),
        *loci.iter().max().expect("nonempty supported loci"),
    )
}

/// Count supported 31-mer positions for every native candidate.
pub(in super::super) fn coverage(depth: &[Vec<u32>]) -> Vec<usize> {
    depth
        .iter()
        .map(|d| d.iter().filter(|&&v| v >= 3).count())
        .collect()
}
