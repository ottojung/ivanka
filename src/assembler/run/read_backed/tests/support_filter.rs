//! Identical or unsupported paths do not gain new remapping targets.
use super::{ranking, scoring};
fn dna(mut state: u64, len: usize) -> Vec<u8> {
    (0..len)
        .map(|_| {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            b"ACGT"[((state >> 28) & 3) as usize]
        })
        .collect()
}

#[test]
fn reject_unsupported_or_redundant_secondaries() {
    let primary = dna(1, 800);
    let copied = primary.clone();
    let unsupported = dna(7, 800);
    let stats = scoring::Statistics {
        depth: vec![],
        pairs: vec![1000, 1000, 20],
        coverage: vec![700, 700, 700],
    };
    assert_eq!(
        ranking::supported_components(&[primary, copied, unsupported], &stats),
        vec![0]
    );
}
