use super::*;

#[test]
fn sliding_query_matches_full_encoder_for_ambiguous_reads() {
    use super::overhang::rolling_query;
    let mut seq = vec![b'A'; 2100];
    let mut rng = 0x8bd530f8b2ac51_u64;
    for (i, x) in seq.iter_mut().enumerate() {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        *x = if i % 127 == 0 {
            b'N'
        } else {
            b"ACGT"[(rng & 3) as usize]
        };
    }
    let mut previous = None;
    for q in 0..=seq.len() - K {
        let current = rolling_query(&seq, q, previous);
        assert_eq!(current, encode(&seq[q..q + K]), "at {q}");
        previous = current;
    }
}
