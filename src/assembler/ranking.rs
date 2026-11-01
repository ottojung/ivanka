use super::ranking_score::ranked_candidates;
use std::collections::HashSet;
use super::reads::{K, encode};

pub(super) fn canonical_kmer(seq:&[u8])->Option<u64> {
    let f=encode(seq)?;
    let mut r=0u64;
    for i in 0..K {r=(r<<2)|(3-((f>>(2*i))&3));}
    Some(f.min(r))
}
fn redundancy(shared:usize,valid:usize,seq:&[u8],longest:usize,support:usize,is_seed:bool)->bool {
    if is_seed||valid==0{return false;}
    if seq.len()<200&&support<10&&longest>0{return true;}
    let short_shadow=seq.len()*4<=longest*3&&shared*20>=valid*17;
    let very_redundant=shared*10>=valid*9;
    let short_redundant=seq.len()<longest&&shared*4>=valid*3&&support<100;
    shared*20>=valid*19||short_shadow||very_redundant||short_redundant
}
pub(super) fn select_supported_contigs(seqs:Vec<Vec<u8>>, counts:Vec<usize>,
                            n:usize, protected:usize)->Vec<Vec<u8>> {
    let candidates=ranked_candidates(seqs,counts,n,protected);
    let mut retained=Vec::new();
    let mut represented=HashSet::new();
    let mut duplicates=0usize;
    let mut no_extension_support=0usize;
    for (index,(seq,support)) in candidates {
        if retained.len()>=n {break;}
        let is_seed=index<protected;
        if !is_seed&&support==0 {no_extension_support+=1;continue;}
        let longest=retained.iter().map(Vec::len).max().unwrap_or(0);
        let mut valid=0usize;let mut shared=0usize;
        for window in seq.windows(K){if let Some(k)=canonical_kmer(window){valid+=1;if represented.contains(&k){shared+=1;}}}
        if redundancy(shared,valid,&seq,longest,support,is_seed){duplicates+=1;continue;}
        for window in seq.windows(K){if let Some(k)=canonical_kmer(window){represented.insert(k);}}
        retained.push(seq);
    }
    eprintln!("IVANKA_QUALITY reported={} kmer_redundant={} no_extension_support={}",
              retained.len(),duplicates,no_extension_support);
    retained
}
