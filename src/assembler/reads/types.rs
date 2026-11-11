use std::cell::{Cell, RefCell};
use std::collections::HashMap;
use std::rc::Rc;
#[derive(Clone, Copy, Debug)]
pub(crate) struct Hit {
    pub(crate) read: u32,
    pub(crate) pos: u16,
}

pub(crate) type ReadOverhangs = (Vec<Vec<u8>>, Vec<u32>);
pub(crate) type OverhangCache = RefCell<HashMap<Vec<u8>, Rc<ReadOverhangs>>>;

pub(crate) struct Reads {
    // Each read and its reverse complement have different index IDs.
    pub(crate) seqs: Vec<Vec<u8>>,
    pub(crate) index: HashMap<u64, Vec<Hit>>,
    pub(crate) seed_counts: HashMap<u64, u32>,
    pub(crate) max_read_len: usize,
    pub(crate) overlength_rejections: Cell<usize>,
    pub(crate) overhang_cache: OverhangCache,
}
