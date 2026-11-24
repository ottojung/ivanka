/// Original-fragment support for the at-most-sixteen default candidates.
pub(in super::super) struct Statistics {
    pub(in super::super) depth: Vec<Vec<u32>>,
    /// Distinct original fragments supporting each contig.
    pub(in super::super) pairs: Vec<usize>,
    /// All observations, including duplicate copies of the same fragment.
    /// Retained only as a tie-break so real abundance is not discarded.
    pub(in super::super) raw_pairs: Vec<usize>,
    pub(in super::super) coverage: Vec<usize>,
    pub(in super::super) pair_masks: Vec<u16>,
}
