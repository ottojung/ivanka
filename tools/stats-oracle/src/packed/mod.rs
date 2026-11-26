//! Exact-head (PR #466, 732b64ca) packed-key index and scoring, vendored verbatim.
//! The shim supplies only the two items the vendored modules import from their
//! original parent (`K` and `Reads`). No production behavior is reimplemented.
mod index;
mod scoring;

pub const K: usize = 31;

pub struct Reads {
    pub seqs: Vec<Vec<u8>>,
}

pub type Stats = (Vec<Vec<u32>>, Vec<usize>, Vec<usize>, Vec<u16>);

pub fn count(contigs: &[Vec<u8>], reads: &Reads) -> Stats {
    let hits = index::build(contigs);
    let s = scoring::count(contigs, reads, &hits);
    (s.depth, s.pairs, s.coverage, s.pair_masks)
}
