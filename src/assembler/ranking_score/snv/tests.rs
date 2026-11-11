use super::*;
#[test]
fn unsupported_single_base_errors_are_not_preserved() {
    let original = vec![b'A'; 200];
    let mut changed = original.clone();
    changed[100] = b'C';
    let mut counts = HashMap::new();
    counts.insert(42, 100);
    let encode = |s: &[u8]| Some(s.iter().map(|b| *b as u64).sum::<u64>());
    assert!(!supported_snv_alternative(
        &changed,
        1,
        std::slice::from_ref(&original),
        &[200],
        &counts,
        encode
    ));
    assert!(!supported_snv_alternative(
        &changed,
        150,
        &[original],
        &[200],
        &HashMap::new(),
        encode
    ));
}
