use super::{dense_spans, output, scoring::Statistics, Reads};

fn reads() -> Reads {
    Reads {
        seqs: vec![],
        index: Default::default(),
        seed_counts: Default::default(),
        max_read_len: 0,
        overlength_rejections: Default::default(),
        overhang_cache: Default::default(),
    }
}

#[test]
fn join_is_replaced_by_two_native_flanks_and_no_bridge() {
    let seq: Vec<u8> = (0..2500).map(|i| b"ACGT"[(i * 7 + i / 13) % 4]).collect();
    let stats = Statistics {
        depth: vec![[vec![120; 1200], vec![4; 70], vec![120; 1200]].concat()],
        pairs: vec![4400],
        coverage: vec![4400],
        spans: vec![dense_spans()],
        ..Statistics::blank(1)
    };
    let parts = output::component(std::slice::from_ref(&seq), &reads(), &stats, 0);
    assert_eq!(parts.len(), 2);
    assert!(parts[0].0.starts_with(">ivanka_1"));
    assert!(parts[1].0.contains("_flank2"));
    for (_, part) in &parts {
        assert!(seq.windows(part.len()).any(|window| window == part));
        assert!(part.len() < seq.len() - 200);
    }
}

#[test]
fn unrelated_high_coverage_components_without_cooccurring_pairs_stay_separate() {
    // PR496 united such components by reading missing co-occurrence as
    // linkage and rotating/concatenating them. Neither inference is valid.
    let a = vec![b'A'; 2500];
    let c = vec![b'C'; 2500];
    let stats = Statistics {
        depth: vec![vec![120; 2470], vec![130; 2470]],
        pairs: vec![4000, 4000],
        coverage: vec![2470, 2470],
        pair_masks: vec![1, 2],
        ..Statistics::blank(2)
    };
    for (chosen, expected) in [(0, &a), (1, &c)] {
        let parts = output::component(&[a.clone(), c.clone()], &reads(), &stats, chosen);
        assert_eq!(parts.len(), 1, "no unsupported unification");
        assert_eq!(&parts[0].1, expected, "native bases and order preserved");
        assert!(!parts[0].0.contains("flank"), "no invented adjacency");
    }
}
