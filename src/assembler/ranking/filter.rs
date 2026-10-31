use super::canonical_kmer;
use std::collections::HashSet;

pub(super) fn select(retained:&mut Vec<Vec<u8>>, represented:&mut HashSet<u64>,
                     duplicates:&mut usize, no_extension_support:&mut usize,
                     index:usize, seq:Vec<u8>, support:usize, protected:usize, _n:usize,
                     high_redundancy:bool){
    if retained.len()>=_n {return;}
    let is_seed=index<protected;
    if !is_seed && support==0 { *no_extension_support+=1; return; }
    let k=super::super::reads::K;
    let mut valid=0usize; let mut shared=0usize;
    for window in seq.windows(k){
        if let Some(k)=canonical_kmer(window){
            valid+=1; if represented.contains(&k){shared+=1;}
        }
    }
    if valid==0 { if is_seed{retained.push(seq);} return; }
    let longest=retained.iter().map(Vec::len).max().unwrap_or(0);
    let short_shadow=seq.len()*4<=longest*3 && shared*20>=valid*17;
    let mut drop=false;
    if is_seed{drop=false;} else if shared*20>=valid*19 || short_shadow{drop=true;}
    else if high_redundancy && shared*100>=valid*95 && support>0{
        let similar_len=retained.iter().any(|r|r.len()*4>=seq.len()*3 && seq.len()*4>=r.len()*3);
        if similar_len && shared*100>=valid*97{drop=true;}
    }
    if drop{*duplicates+=1; return;}
    let k=super::super::reads::K;
    for window in seq.windows(k){ if let Some(km)=canonical_kmer(window){represented.insert(km);} }
    retained.push(seq);
}
