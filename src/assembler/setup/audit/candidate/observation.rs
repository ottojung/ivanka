pub(crate) struct Observation {
    pub(crate) parent: usize,
    pub(crate) pos: usize,
    pub(crate) original: u8,
    pub(crate) alternate: u8,
    pub(crate) length: usize,
    pub(crate) support: usize,
    pub(crate) kmer_witnesses: usize,
    pub(crate) context: String,
}
