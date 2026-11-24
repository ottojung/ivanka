use super::keep_indices;
use std::io::Write;
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT: AtomicUsize = AtomicUsize::new(0);

pub(super) fn seq(seed: u64, len: usize) -> Vec<u8> {
    let mut x = seed;
    (0..len)
        .map(|_| {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            b"ACGT"[(x & 3) as usize]
        })
        .collect()
}

pub(super) fn keep(seed_seqs: &[&[u8]], contigs: &[Vec<u8>]) -> Vec<usize> {
    let name = format!(
        "ivanka-seed-bio-{}-{}.fa",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    );
    let path = std::env::temp_dir().join(name);
    let mut file = std::fs::File::create(&path).unwrap();
    for (index, seed) in seed_seqs.iter().enumerate() {
        writeln!(file, ">s{index}").unwrap();
        file.write_all(seed).unwrap();
        writeln!(file).unwrap();
    }
    drop(file);
    let kept = keep_indices(contigs, path.to_str().unwrap()).unwrap();
    std::fs::remove_file(&path).unwrap();
    kept
}
