use std::collections::HashMap;
use super::index::unique_flanks;
use super::place::original_pair_calls;
// Only original mate pairs that have unique, coherent FR placement count.
pub(super) fn observations(seq: &[u8], reads: &[Vec<u8>], a: usize)
    -> Vec<HashMap<usize,u8>> {
    let index=unique_flanks(seq,a);
    reads.chunks_exact(4).map(|pair|original_pair_calls(pair,&index,a)).collect()
}
