pub(super) fn sequence(length: usize) -> Vec<u8> {
    let mut seq = vec![b'A'; length];
    let mut rng = 0x9a7f_20c3_d6b1_8482_u64;
    for (i, b) in seq.iter_mut().enumerate() {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        *b = if i % 47 == 0 {
            b'N'
        } else {
            b"ACGT"[(rng & 3) as usize]
        };
    }
    seq
}
