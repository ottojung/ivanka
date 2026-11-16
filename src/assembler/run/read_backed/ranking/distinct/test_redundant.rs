use super::redundant::competing;
use super::PairLinks;

fn data() -> (Vec<Vec<u8>>, PairLinks) {
    let contigs = vec![vec![b'A'; 9_626], vec![b'C'; 10_441]];
    let links = [
        ((0, 0), 8_039),
        ((1, 1), 6_179),
        ((0, 1), 5_417),
        ((1, 0), 5_396),
    ]
    .into_iter()
    .collect();
    (contigs, links)
}

#[test]
fn cross_anchored_near_full_length_alternatives_compete() {
    let (contigs, links) = data();
    assert!(competing(1, 0, &contigs, &links));
}

#[test]
fn independent_gap_fragments_are_retained() {
    let (contigs, mut links) = data();
    links.remove(&(0, 1));
    links.remove(&(1, 0));
    assert!(!competing(1, 0, &contigs, &links));
}

#[test]
fn shorter_complement_can_extend_a_representative_path() {
    let (mut contigs, links) = data();
    contigs[1].truncate(4_142);
    assert!(!competing(1, 0, &contigs, &links));
}

#[test]
fn sparse_original_pair_support_is_not_used_to_discard_contig() {
    let (contigs, mut links) = data();
    links.insert((1, 1), 2);
    assert!(!competing(1, 0, &contigs, &links));
}
