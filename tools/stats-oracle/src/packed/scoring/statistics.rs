/// Original-fragment support for the at-most-sixteen default candidates.
pub(in super::super) struct Statistics {
    pub(in super::super) depth: Vec<Vec<u32>>,
    pub(in super::super) pairs: Vec<usize>,
    pub(in super::super) coverage: Vec<usize>,
    pub(in super::super) pair_masks: Vec<u16>,
}

impl Statistics {
    pub(in super::super) fn coverage(depth: &[Vec<u32>]) -> Vec<usize> {
        depth
            .iter()
            .map(|d| d.iter().filter(|&&v| v >= 3).count())
            .collect()
    }
}
