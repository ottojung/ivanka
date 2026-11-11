use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};

mod runner;
pub use runner::{command, fixture};

static NEXT: AtomicUsize = AtomicUsize::new(0);

pub struct Fixture {
    pub(super) dir: PathBuf,
}

impl Fixture {
    pub fn new() -> Self {
        let id = NEXT.fetch_add(1, Ordering::Relaxed);
        let dir = std::env::temp_dir().join(format!("ivanka-contract-{}-{id}", std::process::id()));
        fs::create_dir(&dir).unwrap();
        Self { dir }
    }

    pub fn path(&self, name: &str) -> PathBuf {
        self.dir.join(name)
    }

    pub fn write(&self, name: &str, content: &[u8]) -> PathBuf {
        let path = self.path(name);
        fs::write(&path, content).unwrap();
        path
    }

    pub fn output(&self) -> Vec<u8> {
        fs::read(self.path("output.fasta")).unwrap()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.dir).unwrap();
    }
}
