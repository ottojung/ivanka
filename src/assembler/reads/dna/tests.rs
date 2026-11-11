use super::*;
#[test]
fn reverse_complement() {
    assert_eq!(rc(b"AAGTNC"), b"GNACTT");
}

#[test]
fn encode_roundtrip() {
    let x = b"ACGTACGTACGTACGTACGTACGTACGTACG";
    assert_eq!(decode(encode(x).unwrap()), x);
}

#[test]
fn rolling_canonical_agrees_with_full_window_encoding() {
    let mut rng = 0x123456789abcdef0_u64;
    let mut seq = vec![b'A'; 12000];
    for (i, b) in seq.iter_mut().enumerate() {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        *b = if i % 101 == 0 {
            b'N'
        } else {
            b"ACGT"[(rng & 3) as usize]
        };
    }
    let expected = seq
        .windows(K)
        .filter_map(|w| Some(encode(w)?.min(encode(&rc(w))?)))
        .collect::<Vec<_>>();
    assert_eq!(rolling_canonical_kmers(&seq).collect::<Vec<_>>(), expected);
}
