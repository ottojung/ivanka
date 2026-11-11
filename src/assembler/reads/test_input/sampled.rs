#[test]
fn rolling_seed_counts_match_naive() {
    use super::dna::{encode, rc, K};
    use super::load::count_sampled_seed_kmers;
    use std::collections::HashMap;
    let seq = b"ACGT".repeat(63);
    let mut expected = HashMap::new();
    for i in (0..=seq.len() - K).step_by(3) {
        let f = encode(&seq[i..i + K]).unwrap();
        let r = encode(&rc(&seq[i..i + K])).unwrap();
        *expected.entry(f.min(r)).or_insert(0u32) += 1;
    }
    let mut actual = HashMap::new();
    count_sampled_seed_kmers(&seq, &mut actual);
    assert_eq!(actual, expected);
}
#[test]
fn rolling_seed_counts_handle_ambiguous_bases_and_offset() {
    use super::dna::{encode, rc, K};
    use super::load::count_sampled_seed_kmers;
    use std::collections::HashMap;
    let mut read = b"ACGT".repeat(75);
    for p in [0, 29, 44, 100, 181] {
        read[p] = b'N';
    }
    let (mut expected, mut actual) = (HashMap::new(), HashMap::new());
    for p in (0..=read.len() - K).step_by(3) {
        if let Some(f) = encode(&read[p..p + K]) {
            let r = encode(&rc(&read[p..p + K])).unwrap();
            *expected.entry(f.min(r)).or_insert(0u32) += 1;
        }
    }
    count_sampled_seed_kmers(&read, &mut actual);
    assert_eq!(actual, expected);
}
