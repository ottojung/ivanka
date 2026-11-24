/// Original-fragment support for the at-most-sixteen default candidates.
pub(in super::super) struct Statistics {
    pub(in super::super) depth: Vec<Vec<u32>>,
    pub(in super::super) pairs: Vec<usize>,
    pub(in super::super) coverage: Vec<usize>,
    pub(in super::super) pair_masks: Vec<u16>,
}
