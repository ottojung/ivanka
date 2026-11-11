use super::*;

#[test]
fn cap_respects_protected_prefix_and_1000_limit() {
    let seqs = (1..=1200).map(|n| vec![b'A'; n]).collect::<Vec<_>>();
    let counts = (1..=1200).collect::<Vec<_>>();
    let out = select_supported_contigs(seqs, counts, 1000, 1);
    assert!(out.len() <= 1000);
    assert!(out.len() > 1);
    assert_eq!(out[0].len(), 1);
    assert_eq!(out[1].len(), 1200);
    assert!(!out.iter().any(|s| s.len() == 31));
}
