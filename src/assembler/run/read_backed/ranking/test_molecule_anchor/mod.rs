use super::{molecules::anchor, Hits, K};

pub(super) fn indexed() -> (&'static [u8], Hits) {
    let read = b"ACGTTGACGATTCGAGCTAGTCAGGTACCAGTTGCTTACGGTCACCTTAGGCCTGACATC";
    let mut hits = Hits::new();
    for pos in [0, 26] {
        let key: [u8; K] = read[pos..pos + K].try_into().unwrap();
        hits.insert(key, vec![(0, 5 + pos)]);
    }
    (read, hits)
}

mod negative;
mod positive;
