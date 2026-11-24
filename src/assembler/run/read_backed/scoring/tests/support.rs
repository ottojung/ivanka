use super::{index, Hits, Reads, K};
use std::cell::{Cell, RefCell};
use std::collections::HashMap;

pub(super) fn reads(seqs: Vec<Vec<u8>>) -> Reads {
    let max_read_len = seqs.iter().map(Vec::len).max().unwrap_or(0);
    Reads {
        seqs,
        index: HashMap::new(),
        seed_counts: HashMap::new(),
        max_read_len,
        overlength_rejections: Cell::new(0),
        overhang_cache: RefCell::new(HashMap::new()),
    }
}

pub(super) fn hits(entries: &[(u8, Vec<(usize, usize)>)]) -> Hits {
    let mut map = Hits::new();
    for &(base, ref locations) in entries {
        let key = index::pack(&[base; K]).expect("canonical key");
        map.insert(key, locations.clone());
    }
    map
}

pub(super) fn lcg(state: &mut u64) -> u8 {
    *state = state
        .wrapping_mul(6_364_136_223_846_793_005)
        .wrapping_add(1);
    [b'A', b'C', b'G', b'T'][((*state >> 33) & 3) as usize]
}
