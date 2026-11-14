use super::complement_cases::{choose, random_sequence};

#[test]
fn rejects_small_isolated_artifact() {
    assert_eq!(
        choose(&[random_sequence(42, 2400), random_sequence(7, 160)]),
        None
    );
}

#[test]
fn rejects_reverse_complement_duplicate() {
    let first = random_sequence(42, 2400);
    let other = first
        .iter()
        .rev()
        .map(|b| match b {
            b'A' => b'T',
            b'T' => b'A',
            b'C' => b'G',
            _ => b'C',
        })
        .collect();
    assert_eq!(choose(&[first, other]), None);
}
