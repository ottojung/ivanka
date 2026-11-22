use super::collapse;

#[test]
fn byte_identical_duplicates_collapse() {
    let got = collapse(&[b"ACGT".to_vec(), b"ACGT".to_vec(), b"TTTT".to_vec()]);
    assert_eq!(got, vec![b"ACGT".to_vec(), b"TTTT".to_vec()]);
}

#[test]
fn opposite_strand_duplicates_collapse() {
    let got = collapse(&[b"AACGT".to_vec(), b"ACGTT".to_vec()]);
    assert_eq!(got, vec![b"AACGT".to_vec()]);
}

#[test]
fn distinct_sequences_are_preserved() {
    let seqs: Vec<Vec<u8>> = [b"AACCGG".as_slice(), b"GGCCAA", b"TTTTAA"]
        .iter()
        .map(|s| s.to_vec())
        .collect();
    assert_eq!(collapse(&seqs), seqs);
}

#[test]
fn zero_and_unduplicated_sets_are_noops() {
    assert!(collapse(&[]).is_empty());
    let seqs: Vec<Vec<u8>> = [b"A".as_slice(), b"CC", b"GGG"]
        .iter()
        .map(|s| s.to_vec())
        .collect();
    assert_eq!(collapse(&seqs), seqs);
}

#[test]
fn keeps_first_occurrence_deterministically() {
    let got = collapse(&[b"AC".to_vec(), b"AC".to_vec()]);
    assert_eq!(got, vec![b"AC".to_vec()]);
}
