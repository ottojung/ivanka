/// Original-fragment support for the at-most-sixteen default candidates.
pub(in super::super) struct Statistics {
    pub(in super::super) depth: Vec<Vec<u32>>,
    pub(in super::super) pairs: Vec<usize>,
    pub(in super::super) coverage: Vec<usize>,
    pub(in super::super) pair_masks: Vec<u16>,
    /// Candidates whose exclusive 31-mer loci appear on each original pair.
    /// A locus is exclusive when no other candidate shares its oriented
    /// 31-mer, so these votes distinguish closely related components that
    /// ordinary pair masks cannot separate.
    pub(in super::super) exclusive_masks: Vec<u16>,
    /// One lower-bound read-pair signature per scored pair, in mask order.
    pub(in super::super) pair_signatures: Vec<u64>,
    /// Exclusive locus ranges per candidate as (pair_index, min_locus, max_locus).
    pub(in super::super) exclusive_ranges: Vec<Vec<(u32, u32, u32)>>,
    /// Extreme mapped loci of each supporting original pair, per candidate.
    pub(in super::super) spans: Vec<Vec<(usize, usize)>>,
}

#[cfg(test)]
impl Statistics {
    pub(in super::super) fn blank(n: usize) -> Self {
        Self {
            depth: vec![],
            pairs: vec![0; n],
            coverage: vec![0; n],
            pair_masks: Vec::new(),
            exclusive_masks: Vec::new(),
            pair_signatures: Vec::new(),
            exclusive_ranges: vec![Vec::new(); n],
            spans: vec![vec![]; n],
        }
    }
}
