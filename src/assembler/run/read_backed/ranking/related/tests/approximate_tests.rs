use super::{
    approximate_fixtures::{diverged, fixture, path, revcomp},
    approximate_junction, pieces_keep_middle, short_seed,
};

fn first() -> Vec<u8> {
    path(0x1234_5678_9abc_def0, 4000)
}

#[test]
fn canonical_seed_is_strand_invariant() {
    let word = b"AACC".to_vec();
    assert_eq!(revcomp(&word), b"GGTT".to_vec());
    assert_eq!(short_seed(&word), short_seed(&revcomp(&word)));
    let seq = first();
    assert_eq!(short_seed(&seq), short_seed(&revcomp(&seq)));
}

#[test]
fn approximate_repeat_split_keeps_every_supported_base() {
    let (seq, depth, spans) = fixture(diverged(&first()), false);
    assert_eq!(
        approximate_junction(&seq, &depth, &spans),
        Some((2000, 5000))
    );
    let parts = pieces_keep_middle((2000, 5000), seq.len());
    assert_eq!(parts.len(), 3);
    assert_eq!(parts.iter().map(|&(a, b)| b - a).sum::<usize>(), seq.len());
    for &(a, b) in &parts {
        assert!(seq.windows(b - a).any(|window| window == &seq[a..b]));
    }
    assert!(parts[1].1 - parts[1].0 > 2000);
}

#[test]
fn spanning_pairs_and_similarity_controls_block_the_split() {
    let (seq, depth, spans) = fixture(diverged(&first()), true);
    assert_eq!(approximate_junction(&seq, &depth, &spans), None);
    let unit = path(0x0bad_c0de_dead_beef, 150);
    let mut tandem = Vec::new();
    for _ in 0..30 {
        tandem.extend_from_slice(&unit);
    }
    let (seq, depth, spans) = fixture(tandem, false);
    assert_eq!(approximate_junction(&seq, &depth, &spans), None);
    let (seq, depth, spans) = fixture(path(0xdead_beef_1234_5678, 4000), false);
    assert_eq!(approximate_junction(&seq, &depth, &spans), None);
    let clonal = path(0x0102_0304_0506_0708, 5000);
    let depth = vec![120u32; clonal.len() - 30];
    assert_eq!(approximate_junction(&clonal, &depth, &[(0, 1400)]), None);
}
