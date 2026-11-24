/// Original-fragment support for the at-most-sixteen default candidates.
pub(in super::super) struct Statistics {
    pub(in super::super) depth: Vec<Vec<u32>>,
    pub(in super::super) pairs: Vec<usize>,
    pub(in super::super) coverage: Vec<usize>,
    /// Candidates seen on each original pair (at least two distinct loci).
    pub(in super::super) pair_masks: Vec<u16>,
    /// Candidates whose *exclusive* 31-mer loci appear on each pair. A locus
    /// is exclusive when no other candidate shares its oriented 31-mer, so
    /// these votes distinguish closely related components that ordinary
    /// pair masks cannot separate.
    pub(in super::super) exclusive_masks: Vec<u16>,
}
