mod pairs;
pub use self::pairs::{read_pairs, write_pairs};
use std::path::PathBuf;

pub fn dir(name: &str) -> PathBuf {
    let path =
        std::env::temp_dir().join(format!("ivanka-p0-canary-{}-{}", std::process::id(), name));
    let _ = std::fs::remove_dir_all(&path);
    std::fs::create_dir_all(&path).unwrap();
    path
}

pub fn template(len: usize, salt: u64) -> String {
    let mut state = salt | 1;
    (0..len)
        .map(|_| {
            state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
            b"ACGT"[((state >> 33) & 3) as usize] as char
        })
        .collect()
}

pub fn reverse(seq: &str) -> String {
    seq.chars()
        .rev()
        .map(|base| match base {
            'A' => 'T',
            'C' => 'G',
            'G' => 'C',
            _ => 'A',
        })
        .collect()
}
