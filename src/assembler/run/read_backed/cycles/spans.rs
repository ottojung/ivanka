//! Exact long windows distinguish read-supported overlap from a short-repeat join.
use super::Reads;
use std::collections::HashMap;
const SPAN: usize = 101;

pub(super) fn count(sequence: &[u8], reads: &Reads) -> Vec<u16> {
    let mut loci = HashMap::<&[u8], Vec<usize>>::new();
    for (position, word) in sequence.windows(SPAN).enumerate() {
        loci.entry(word).or_default().push(position);
    }
    let mut depth = vec![0_u16; sequence.len() - SPAN + 1];
    for read in reads.seqs.chunks_exact(4).take(80_000).flatten() {
        for window in read.windows(SPAN) {
            if let Some(positions) = loci.get(window) {
                for &position in positions {
                    depth[position] = depth[position].saturating_add(1);
                }
            }
        }
    }
    depth
}
