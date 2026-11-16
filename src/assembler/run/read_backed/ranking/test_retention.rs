use super::{should_add, Entry, PairLinks, Statistics};

fn records(len: usize) -> Vec<Entry> {
    vec![("assembled".into(), vec![b'A'; len])]
}

fn stats(pairs: [usize; 2], coverage: [usize; 2]) -> Statistics {
    Statistics {
        depth: vec![],
        pairs: pairs.to_vec(),
        coverage: coverage.to_vec(),
    }
}

#[test]
fn sparse_near_full_length_path_is_withheld_after_emission() {
    let contigs = vec![vec![b'A'; 324], vec![b'C'; 306]];
    let mut support = stats([402, 47], [286, 222]);
    let links = PairLinks::new();
    assert!(!should_add(
        0,
        1,
        &contigs,
        &support,
        &links,
        &records(324),
        &records(306)
    ));
    support.pairs[1] = 200;
    assert!(should_add(
        0,
        1,
        &contigs,
        &support,
        &links,
        &records(324),
        &records(306)
    ));
}

mod cross;

mod gap;
