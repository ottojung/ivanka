use super::canonical_kmer;
use std::collections::HashSet;

pub(super) fn recover(retained:&mut Vec<Vec<u8>>, represented:&mut HashSet<u64>, duplicates:&mut usize,
                      candidates:&Vec<(usize,(Vec<u8>,usize))>, protected:usize, n:usize){
    if retained.len()>=n || *duplicates<=n || candidates.len()<=n.saturating_mul(3){return;}
    let k=crate::assembler::reads::K;
    let mut seen_lens:HashSet<usize>=HashSet::new();
    for s in retained.iter(){ seen_lens.insert(s.len()/10*10); }
    for (index,(seq,support)) in candidates.iter(){
        if retained.len()>=n {break;}
        if *index<protected||*support==0 {continue;}
        let mut valid=0usize; let mut shared=0usize;
        for window in seq.windows(k){ if let Some(km)=canonical_kmer(window){valid+=1; if represented.contains(&km){shared+=1;} } }
        if valid>0&&shared*100>=valid*99 {continue;}
        let bucket=seq.len()/10*10;
        if seen_lens.contains(&bucket){continue;}
        let seqc=seq.clone();
        for window in seqc.windows(k){ if let Some(km)=canonical_kmer(window){represented.insert(km);} }
        retained.push(seqc); seen_lens.insert(bucket); *duplicates+=1;
    }
}
