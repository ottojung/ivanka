use super::*;
#[test]
fn exact_suffix_cache_matches_fresh_query() {
    let contig = b"ACGT".repeat(100);
    let mut read = contig[290..].to_vec();
    read.extend_from_slice(b"AG");
    let reads = Reads {
        max_read_len: read.len(),
        seqs: vec![read.clone()],
        index: super::build_index(&[read]),
        seed_counts: Default::default(),
        overhang_cache: Default::default(),
        overlength_rejections: Default::default(),
    };
    let original = reads.cached_overhangs(&contig);
    let mut extended = b"TGCA".repeat(20);
    extended.extend_from_slice(&contig);
    let repeated = reads.cached_overhangs(&extended);
    assert!(Rc::ptr_eq(&original, &repeated));
    assert!(!original.0.is_empty());
    assert_eq!(*original, reads.overhangs_with_ids(&extended));
}

#[test]
fn short_sequences_have_distinct_keys_and_cache_stays_bounded() {
    let reads = Reads {
        max_read_len: 300,
        seqs: Vec::new(),
        index: Default::default(),
        seed_counts: Default::default(),
        overhang_cache: Default::default(),
        overlength_rejections: Default::default(),
    };
    let first = reads.cached_overhangs(b"ACGTACGT");
    let second = reads.cached_overhangs(b"TCGTACGT");
    assert!(!Rc::ptr_eq(&first, &second));
    for i in 0..300u32 {
        reads.cached_overhangs(&i.to_le_bytes());
    }
    assert!(reads.overhang_cache.borrow().len() <= 256);
    assert_eq!(*first, reads.overhangs_with_ids(b"ACGTACGT"));
}
