use super::locate_strict;

fn scan(length: usize, gaps: &[(usize, usize)]) -> Option<usize> {
    let seq = vec![b'A'; length];
    let mut position = 0;
    locate_strict(&seq, |_| {
        let p = position;
        position += 1;
        !gaps.iter().any(|&(a, b)| (a..b).contains(&p))
    })
}

#[test]
fn rejects_one_outlier_without_losing_dominant_gap() {
    assert_eq!(scan(15024, &[(5309, 5391), (9394, 9395)]), Some(5412));
}

#[test]
fn rejects_two_real_independent_unbridged_junctions() {
    assert_eq!(scan(15024, &[(5309, 5391), (9394, 9480)]), None);
}

#[test]
fn rejects_multiple_isolated_dropout_windows() {
    assert_eq!(scan(15024, &[(5309, 5391), (9394, 9399)]), None);
}
