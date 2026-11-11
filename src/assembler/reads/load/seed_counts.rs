use super::{HashMap, K};
pub(crate) fn count_sampled_seed_kmers(read: &[u8], counts: &mut HashMap<u64, u32>) {
    let (mut f, mut r, mut valid) = (0u64, 0u64, 0usize);
    for (i, &b) in read.iter().enumerate() {
        let d = match b {
            b'A' => 0,
            b'C' => 1,
            b'G' => 2,
            b'T' => 3,
            _ => {
                f = 0;
                r = 0;
                valid = 0;
                continue;
            }
        };
        f = ((f << 2) & ((1u64 << 62) - 1)) | d;
        r = (r >> 2) | ((3 - d) << 60);
        valid += 1;
        if valid >= K && (i + 1 - K) % 3 == 0 {
            *counts.entry(f.min(r)).or_insert(0) += 1;
        }
    }
}
