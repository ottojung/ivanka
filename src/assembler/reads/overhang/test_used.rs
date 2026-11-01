use super::{Reads,K,encode,Hit};

#[test]
fn bitset_deduplicates_orientations_and_handles_odd_read_count() {
    let contig=b"ACGT".repeat(10);
    let mut read=contig.clone();
    read.push(b'T');
    let mut index=std::collections::HashMap::new();
    index.insert(encode(&contig[..K]).unwrap(),
                 vec![Hit{read:0,pos:0},Hit{read:1,pos:0},Hit{read:2,pos:0}]);
    let reads=Reads{seqs:vec![read.clone(),read.clone(),read],index,
        max_read_len:41,seed_counts:Default::default(),
        overhang_cache:Default::default(),overlength_rejections:Default::default(),seen:Default::default()};
    let (overhangs,ids)=reads.overhangs_with_ids(&contig);
    assert_eq!(ids,vec![0,1]);
    assert_eq!(overhangs,vec![vec![b'T'],vec![b'T']]);
}

#[test]
fn terminal_index_dedup_preserves_repetitive_high_depth_overhangs() {
    let mut seqs=Vec::with_capacity(40_000);
    for _ in 0..20_000 {
        seqs.push(vec![b'A';43]);
        seqs.push(vec![b'T';43]);
    }
    let index=super::build_index(&seqs);
    let anchor=encode(&vec![b'A';K]).unwrap();
    assert_eq!(index[&anchor].len(),40_000);
    let reads=Reads{seqs,index,max_read_len:43,seed_counts:Default::default(),
        overhang_cache:Default::default(),overlength_rejections:Default::default(),seen:Default::default()};
    let (overhangs,ids)=reads.overhangs_with_ids(&vec![b'A';K]);
    assert_eq!(ids.len(),20_000);
    assert!(overhangs.iter().all(|suffix|suffix==&vec![b'A';12]));
}
