use super::Probe;
// Empty slices represent a deliberately stalled direction, not a
// zero-support observation that requires another index lookup.
impl Probe {
    pub(crate) fn right_refs(&self) -> (&[Vec<u8>], &[u32]) {
        match &self.right_cached {
            Some(pair) => (pair.0.as_slice(), pair.1.as_slice()),
            None => (&[], &[]),
        }
    }
    pub(crate) fn left_refs(&self) -> (&[Vec<u8>], &[u32]) {
        match &self.left_cached {
            Some(pair) => (pair.0.as_slice(), pair.1.as_slice()),
            None => (&[], &[]),
        }
    }
}
