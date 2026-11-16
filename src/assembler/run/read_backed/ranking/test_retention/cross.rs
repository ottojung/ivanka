use super::{records, should_add, stats};

#[test]
fn strong_cross_mate_linked_alternative_is_withheld() {
    let contigs = vec![vec![b'A'; 9_626], vec![b'C'; 10_441]];
    let support = stats([8_590, 7_253], [9_592, 10_408]);
    let links = [
        ((0, 0), 8_039),
        ((1, 1), 6_179),
        ((0, 1), 5_417),
        ((1, 0), 5_396),
    ]
    .into_iter()
    .collect();
    assert!(!should_add(
        0,
        1,
        &contigs,
        &support,
        &links,
        &records(9_626),
        &records(10_441)
    ));
}
