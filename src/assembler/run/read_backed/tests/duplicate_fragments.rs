use super::{index, ranking, scoring, Reads};

fn sequence(len: usize, seed: u64) -> Vec<u8> {
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

fn add_pair(seqs: &mut Vec<Vec<u8>>, fragment: &[u8], copies: usize) {
    for _ in 0..copies {
        seqs.extend([
            fragment.to_vec(),
            fragment.to_vec(),
            fragment.to_vec(),
            fragment.to_vec(),
        ]);
    }
}

/// A contig backed by two repeated pair sequences must not outrank a contig
/// backed by many distinct observations. Raw frequency remains available only
/// as an exact tie-break.
#[test]
fn repeated_pair_sequences_cannot_outvote_distinct_evidence() {
    let diverse = sequence(240, 1);
    let jackpot = sequence(90, 2);
    let contigs = vec![diverse.clone(), jackpot.clone()];
    let mut seqs = Vec::new();
    for start in (0..=diverse.len() - 60).step_by(10) {
        add_pair(&mut seqs, &diverse[start..start + 60], 3);
    }
    for start in [0, 30] {
        add_pair(&mut seqs, &jackpot[start..start + 60], 500);
    }
    let reads = Reads {
        seqs,
        index: Default::default(),
        seed_counts: Default::default(),
        max_read_len: 60,
        overlength_rejections: Default::default(),
        overhang_cache: Default::default(),
    };
    let stats = scoring::count(&contigs, &reads, &index::build(&contigs));
    assert_eq!(stats.pairs, vec![19, 2], "distinct-fragment support");
    assert_eq!(stats.raw_pairs, vec![57, 1000], "raw abundance kept");
    assert_eq!(ranking::best(&contigs, &stats), 0, "diverse must win");
}
