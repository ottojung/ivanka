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
        overhang_cache:Default::default(),overlength_rejections:Default::default()};
    let (overhangs,ids)=reads.overhangs_with_ids(&contig);
    assert_eq!(ids,vec![0,1]);
    assert_eq!(overhangs,vec![vec![b'T'],vec![b'T']]);
}
