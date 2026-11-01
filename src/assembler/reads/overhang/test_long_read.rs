use std::collections::HashMap;
use super::{encode,K,rc,Reads,build_index};
#[test]
fn long_read_extends_across_ambiguous_suffix_without_losing_its_anchor() {
    // The only valid 31-mer anchors precede the last 250 bases. A 250-base
    // hard-coded scan therefore loses an exact, extension-bearing long read.
    let mut contig=b"ACGT".repeat(12);
    contig.extend_from_slice(b"AA");
    contig.extend_from_slice(&vec![b'N';250]);
    let extension=b"GATTACAGATTA";
    let mut read=contig.clone();
    read.extend_from_slice(extension);
    let seqs=vec![read.clone(),rc(&read)];
    let reads=Reads{index:build_index(&seqs),seqs,
        max_read_len:read.len(),seed_counts:HashMap::new(),
        overhang_cache:Default::default(),overlength_rejections:Default::default()};
    assert!(contig[contig.len()-250..].windows(K).all(|w|encode(w).is_none()));
    assert_eq!(reads.overhangs_with_ids(&contig),
               (vec![extension.to_vec()],vec![0]));
}
