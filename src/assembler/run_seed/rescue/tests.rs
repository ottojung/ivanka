use super::*;
#[test]
fn only_high_depth_short_assemblies_get_fallback() {
    assert!(eligible(None, 40004, 715, 100));
    assert!(!eligible(None, 40000, 715, 100));
    assert!(!eligible(Some(20000), 40004, 715, 100));
    assert!(!eligible(None, 40004, 1000, 100));
    assert!(!eligible(None, 40004, 715, 0));
}

#[test]
fn bounded_rescue_prefers_supported_span() {
    let original = vec![vec![b'T'; 150]];
    let more = vec![vec![b'A'; 1200], vec![b'C'; 2300], vec![b'G'; 700]];
    let (seq, support) = best_long(more, vec![10, 8, 100], &original).unwrap();
    assert_eq!((seq.len(), support), (2300, 8));
}
