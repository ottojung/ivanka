use super::*;

#[test]
fn stable_suffix_overhangs_ignore_left_prepend() {
    use super::index::build_index;
    let contig = b"ACGT".repeat(100);
    let mut read = contig[290..].to_vec();
    read.extend_from_slice(b"AG");
    let max_read_len = read.len();
    let index = build_index(&[read.clone()]);
    let reads = Reads {
        seqs: vec![read],
        index,
        seed_counts: HashMap::new(),
        max_read_len,
        overhang_cache: Default::default(),
        overlength_rejections: Default::default(),
    };
    assert!(contig.len() >= reads.max_read_len);
    let original = reads.overhangs_with_ids(&contig);
    let mut prefixed = b"TGCA".repeat(20);
    prefixed.extend_from_slice(&contig);
    let changed = reads.overhangs_with_ids(&prefixed);
    assert!(!original.0.is_empty());
    assert_eq!(original, changed);
}
