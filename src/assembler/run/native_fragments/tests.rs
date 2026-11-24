use super::Reads;

pub(super) fn sequence(len: usize, seed: u64) -> Vec<u8> {
    const BASES: [u8; 4] = [b'A', b'C', b'G', b'T'];
    let mut state = seed;
    (0..len)
        .map(|_| {
            state = state
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1_442_695_040_888_963_407);
            BASES[(state >> 33) as usize % 4]
        })
        .collect()
}

pub(super) fn reads() -> Reads {
    Reads {
        seqs: Vec::new(),
        index: Default::default(),
        seed_counts: Default::default(),
        max_read_len: 60,
        overlength_rejections: Default::default(),
        overhang_cache: Default::default(),
    }
}

pub(super) fn repeated_fragment(fragment: &[u8], distinct_mates: usize) -> Vec<Vec<u8>> {
    let mut seqs = Vec::new();
    for n in 0..distinct_mates {
        let mate = sequence(60, 100 + n as u64);
        seqs.extend([fragment.to_vec(), fragment.to_vec(), mate.clone(), mate]);
    }
    seqs
}

#[test]
fn retains_distinct_read_supported_region() {
    let fragment = sequence(60, 2);
    let mut contigs = vec![sequence(240, 1)];
    let mut data = reads();
    data.seqs = repeated_fragment(&fragment, 20);
    assert_eq!(super::retain(&mut contigs, &data, 16, None).unwrap(), 1);
    assert_eq!(contigs[1], fragment, "retained contig is one observed read");
}
