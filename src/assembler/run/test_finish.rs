use super::Reads;
use std::cell::{Cell, RefCell};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT: AtomicUsize = AtomicUsize::new(0);

pub(super) fn reads(counts: HashMap<u64, u32>) -> Reads {
    Reads {
        seqs: Vec::new(),
        index: HashMap::new(),
        seed_counts: counts,
        max_read_len: 0,
        overlength_rejections: Cell::new(0),
        overhang_cache: RefCell::new(HashMap::new()),
    }
}

pub(super) struct Dir(PathBuf);
impl Dir {
    pub(super) fn new() -> Self {
        let id = NEXT.fetch_add(1, Ordering::Relaxed);
        let dir = std::env::temp_dir().join(format!("ivanka-finish-{}-{id}", std::process::id()));
        std::fs::create_dir(&dir).unwrap();
        Self(dir)
    }
    pub(super) fn out(&self) -> String {
        self.0.join("contigs.fasta").to_str().unwrap().to_owned()
    }
}
impl Drop for Dir {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).unwrap();
    }
}
