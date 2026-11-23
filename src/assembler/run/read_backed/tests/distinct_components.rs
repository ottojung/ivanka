//! Source-blind component admission: original-pair supported, novel 31-mers.
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
fn retain_a_separate_550_base_component_at_fifteen_percent() {
    let contigs = vec![dna(1, 9635), dna(7, 550)];
    let stats = scoring::Statistics {
        depth: vec![],
        pairs: vec![8524, 1500],
        coverage: vec![9581, 519],
    };
    assert_eq!(ranking::supported_components(&contigs, &stats), vec![0, 1]);
}

#[test]
fn retain_two_disconnected_read_supported_coverage_islands() {
    let contigs = vec![dna(1, 4437), dna(7, 4145)];
    let stats = scoring::Statistics {
        depth: vec![],
        pairs: vec![5205, 3300],
        coverage: vec![4404, 4112],
    };
    assert_eq!(ranking::supported_components(&contigs, &stats), vec![0, 1]);
}
