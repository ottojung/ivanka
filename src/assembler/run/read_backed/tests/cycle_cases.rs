use super::{detect, variants};

#[test]
fn overlap_is_exact_and_not_merely_an_internal_repeat() {
    assert_eq!(detect::terminal_overlap(b"ACGTTTACG"), 3);
    assert_eq!(detect::terminal_overlap(b"ACGTCCGA"), 1);
    assert_eq!(detect::terminal_overlap(b""), 0);
}

#[test]
fn isolated_unsupported_long_span_is_found_without_references() {
    let mut depth = vec![17_u16; 9000];
    depth[4300..4358].fill(0);
    assert_eq!(detect::unsupported_gap(&depth), Some((4300, 4358)));
    depth[1000..1400].fill(0);
    assert_eq!(detect::unsupported_gap(&depth), None);
}

#[test]
fn terminal_or_small_unsupported_spans_are_not_used_as_breaks() {
    let mut depth = vec![17_u16; 9000];
    depth[5..90].fill(0);
    depth[5000..5015].fill(0);
    assert_eq!(detect::unsupported_gap(&depth), None);
}

#[test]
fn both_rotations_preserve_the_same_cyclic_source_bases() {
    let sequence: Vec<u8> = (0..300).map(|i| b"ACGTT"[i % 5]).collect();
    let variants = variants::build(">s", &sequence, 2, 103, 105);
    assert_eq!(variants.len(), 2);
    assert_eq!(variants[0].1.len(), sequence.len());
    assert_eq!(variants[1].1.len(), sequence.len());
    let expected = sequence[..298]
        .iter()
        .cycle()
        .skip(105)
        .take(300)
        .copied()
        .collect::<Vec<_>>();
    assert_eq!(variants[0].1, expected);
    assert!(variants[0].0.contains("opening1"));
    assert!(variants[1].0.contains("opening2"));
}
