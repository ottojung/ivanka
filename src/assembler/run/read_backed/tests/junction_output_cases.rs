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
    let seq = (0..2500)
        .map(|i| b"ACGT"[(i * 7 + i / 13) % 4])
        .collect::<Vec<u8>>();
    let stats = Statistics {
        depth: vec![[vec![120; 1200], vec![4; 70], vec![120; 1200]].concat()],
        pairs: vec![4400],
        coverage: vec![4400],
        pair_masks: vec![],
        spans: vec![dense_spans()],
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
fn unrelated_uniform_components_are_never_joined_or_split() {
    let seq = (0..2500)
        .map(|i| b"ACGT"[(i * 5 + i / 7) % 4])
        .collect::<Vec<u8>>();
    let stats = Statistics {
        depth: vec![vec![100; 2470], vec![110; 2470]],
        pairs: vec![4000, 4000],
        coverage: vec![2470, 2470],
        pair_masks: vec![],
        spans: vec![vec![], vec![]],
    };
    for chosen in 0..2 {
        let parts = output::component(&[seq.clone(), seq.clone()], &reads(), &stats, chosen);
        assert_eq!(parts.len(), 1);
        assert_eq!(parts[0].1, seq);
    }
}
