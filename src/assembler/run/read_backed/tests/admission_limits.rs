//! All component evidence and default-output limits are checked without truth.
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
fn cannot_admit_less_than_one_eighth_primary_pair_evidence() {
    let contigs = vec![dna(1, 1000), dna(7, 700)];
    let stats = scoring::Statistics {
        depth: vec![],
        pairs: vec![1600, 199],
        coverage: vec![970, 670],
    };
    assert_eq!(ranking::supported_components(&contigs, &stats), vec![0]);
}

#[test]
fn never_exceed_sixteen_default_contigs_despite_many_components() {
    let contigs = (1..=25).map(|i| dna(i * 11, 650)).collect::<Vec<_>>();
    let stats = scoring::Statistics {
        depth: vec![],
        pairs: vec![500; 25],
        coverage: vec![620; 25],
    };
    let kept = ranking::supported_components(&contigs, &stats);
    assert_eq!(kept.len(), 16);
    assert_eq!(kept[0], 0);
}
