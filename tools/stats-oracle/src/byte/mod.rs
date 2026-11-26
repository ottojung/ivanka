//! Byte-key baseline (PR #463 reviewer head, 47ee44c2) index and scoring,
//! vendored verbatim. Used as an independent cross-check of the packed path.
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
