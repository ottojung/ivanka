use std::collections::HashMap;
#[derive(Clone, Copy, Debug)]
pub(crate) struct Hit { pub(crate) read: u32, pub(crate) pos: u16 }

pub(crate) struct Reads {
    pub(crate) seqs: Vec<Vec<u8>>,  // forward and reverse complement; index by orientation-specific ID
    pub(crate) index: HashMap<u64, Vec<Hit>>,
    pub(crate) seed_counts: HashMap<u64, u32>,
    pub(crate) max_read_len: usize,
}
