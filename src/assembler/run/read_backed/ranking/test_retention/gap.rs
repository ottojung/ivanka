use super::{records, should_add, stats, PairLinks};

#[test]
fn emitted_short_fragments_survive_even_if_original_path_was_long() {
    let contigs = vec![vec![b'A'; 11_760], vec![b'C'; 11_900]];
    let support = stats([9_000, 150], [11_720, 11_800]);
    let links = PairLinks::new();
    let extra = vec![
        ("part1".into(), vec![b'C'; 6_282]),
        ("part2".into(), vec![b'G'; 4_919]),
    ];
    assert!(should_add(
        0,
        1,
        &contigs,
        &support,
        &links,
        &records(11_760),
        &extra
    ));
}

#[test]
fn disjoint_coverage_gap_fragments_are_retained() {
    let contigs = vec![vec![b'A'; 4_428], vec![b'C'; 4_142]];
    let support = stats([5_157, 4_843], [4_400, 4_100]);
    assert!(should_add(
        0,
        1,
        &contigs,
        &support,
        &PairLinks::new(),
        &records(4_428),
        &records(4_142)
    ));
}
