// Exact containment (either strand) preserves full phased source paths.
pub(super) fn contains_or_rc(haystack:&[u8],needle:&[u8])->bool {
    if needle.is_empty() {return true;}
    if needle.len()>haystack.len() {return false;}
    let rc=needle.iter().rev().map(|b|match b {
        b'A'=>b'T',b'T'=>b'A',b'C'=>b'G',b'G'=>b'C',b'N'=>b'N',other=>*other
    }).collect::<Vec<_>>();
    haystack.windows(needle.len()).any(|w|w==needle || w==rc)
}
#[test] fn both_strands_are_equivalent() {
    assert!(contains_or_rc(b"GGGACGTTT",b"AACGT"));
    assert!(contains_or_rc(b"GGGAACGTT",b"AACGT"));
    assert!(!contains_or_rc(b"GGGACGTTT",b"AACGA"));
}
