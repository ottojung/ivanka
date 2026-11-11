use std::collections::{HashMap, HashSet};
pub(super) fn kmer(seq: &[u8]) -> Option<u64> {
    let mut x = 0u64;
    for &b in seq {
        let v = match b {
            b'A' => 0,
            b'C' => 1,
            b'G' => 2,
            b'T' => 3,
            _ => return None,
        };
        x = (x << 2) | v;
    }
    Some(x)
}
pub(super) fn example() -> (Vec<u8>, Vec<u8>, HashMap<u64, u32>) {
    let mut seed = 0x9e3779b97f4a7c15u64;
    let original = (0..300)
        .map(|_| {
            seed ^= seed << 13;
            seed ^= seed >> 7;
            seed ^= seed << 17;
            b"ACGT"[(seed & 3) as usize]
        })
        .collect::<Vec<_>>();
    let mut variant = original.clone();
    variant[150] = if variant[150] == b'A' { b'C' } else { b'A' };
    let baseline = original
        .windows(31)
        .filter_map(kmer)
        .collect::<HashSet<_>>();
    let counts = variant
        .windows(31)
        .filter_map(kmer)
        .filter(|x| !baseline.contains(x))
        .map(|x| (x, 10))
        .collect();
    (original, variant, counts)
}
pub(super) fn output_path(label: &str) -> String {
    format!(
        "/tmp/ivanka_snv_audit_{}_{}_{}.tsv",
        std::process::id(),
        label,
        std::thread::current().name().unwrap_or("test")
    )
}
