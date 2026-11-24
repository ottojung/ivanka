use super::*;

fn path(seed: u64, len: usize) -> Vec<u8> {
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

#[test]
fn read_supported_minority_haplotype_is_retained_at_short_length() {
    let major = path(0x5eed_1520, 310);
    let mut minority = major.clone();
    minority[150] = if minority[150] == b'A' { b'C' } else { b'A' };
    // About 85:15 read support: a distinct haplotype, not a redundant copy.
    let kept = select_supported_contigs(vec![major, minority.clone()], vec![850, 150], 16, 0);
    assert!(
        kept.contains(&minority),
        "a read-supported short minority contig must survive selection"
    );
}
