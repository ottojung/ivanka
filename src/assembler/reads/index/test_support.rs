use std::collections::HashSet;
use super::{Reads,build_index,rc,rolling_canonical_kmers,encode,read_backed_novel};
fn canonical(seq:&[u8])->Option<u64> {
    Some(encode(seq)?.min(encode(&rc(seq))?))
}
pub(super) fn example(n:usize,reverse_only:bool)->(Vec<u8>,Vec<u8>,Reads) {
    let mut state=0x123456789abcdef0u64;
    let mut base=Vec::new();
    for _ in 0..1200 {
        state^=state<<13;state^=state>>7;state^=state<<17;
        base.push(b"ACGT"[(state&3) as usize]);
    }
    let mut variant=base.clone();
    variant[600]=match base[600] {b'A'=>b'C',_=>b'A'};
    let mut seqs=Vec::new();
    for j in 0..n {
        let start=530+j%21;
        let read=variant[start..start+150].to_vec();
        if reverse_only {seqs.push(rc(&read));seqs.push(read);}
        else {seqs.push(read.clone());seqs.push(rc(&read));}
    }
    let index=build_index(&seqs);
    (base,variant,Reads{index,seqs,max_read_len:150,
        seed_counts:Default::default(),overhang_cache:Default::default(),
        overlength_rejections:Default::default()})
}
#[test] fn local_allele_requires_ten_distinct_read_records() {
    for n in [1,9,10,11] {
        let (base,variant,reads)=example(n,false);
        let represented=rolling_canonical_kmers(&base).collect::<HashSet<_>>();
        assert_eq!(read_backed_novel(&variant,&represented,&reads,canonical),n>=10);
    }
}
#[test] fn reverse_orientation_is_supported_but_not_double_counted() {
    for n in [9,10] {
        let (base,variant,reads)=example(n,true);
        let represented=rolling_canonical_kmers(&base).collect::<HashSet<_>>();
        assert_eq!(read_backed_novel(&variant,&represented,&reads,canonical),n>=10);
    }
}
#[test] fn no_novel_31mer_cannot_be_rescued() {
    let (base,_,reads)=example(12,false);
    let represented=rolling_canonical_kmers(&base).collect::<HashSet<_>>();
    assert!(!read_backed_novel(&base,&represented,&reads,canonical));
}
