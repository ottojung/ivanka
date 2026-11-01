use super::Seen;
#[test]
fn sparse_bitset_reuses_words_without_retaining_previous_query() {
    let mut seen = Seen::default();
    for id in [0, 1, 63, 64, 127, 1024] {
        assert!(!seen.contains(id));
        seen.mark(id);
        assert!(seen.contains(id));
    }
    assert_eq!(seen.touched.len(), 3);
    let allocated = seen.words.len();
    seen.clear();
    assert_eq!(seen.words.len(), allocated);
    assert!(seen.touched.is_empty());
    for id in [0, 1, 63, 64, 127, 1024] { assert!(!seen.contains(id)); }
    seen.mark(127);
    assert!(seen.contains(127));
    assert!(!seen.contains(64));
    seen.clear();
}
#[test]
fn successive_exact_read_queries_do_not_reuse_stale_ids() {
    use super::{Reads, build_index, rc};
    let mut a = vec![b'A'; 40]; a.push(b'C');
    let mut b = vec![b'T'; 40]; b.push(b'G');
    let seqs = vec![a.clone(), rc(&a), b.clone(), rc(&b)];
    let reads = Reads { index: build_index(&seqs), seqs, max_read_len: 41,
        seed_counts: Default::default(), overhang_cache: Default::default(),
        overlength_rejections: Default::default(), seen: Default::default() };
    let q1 = vec![b'A'; 40];
    let q2 = vec![b'T'; 40];
    assert_eq!(reads.overhangs_with_ids(&q1), (vec![vec![b'C']], vec![0]));
    assert_eq!(reads.overhangs_with_ids(&q2), (vec![vec![b'G']], vec![1]));
    assert_eq!(reads.overhangs_with_ids(&q1), (vec![vec![b'C']], vec![0]));
}
