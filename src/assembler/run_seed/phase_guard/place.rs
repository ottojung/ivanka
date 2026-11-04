use std::collections::HashMap;
use super::index::{kmer_codes,INVALID,ReadPrep};
use super::quality_filter::valid_window;
struct Placement{start:isize,end:isize,calls:HashMap<usize,u8>}
fn locate_cached(read:&[u8],prep:&ReadPrep,index:&HashMap<u128,Option<usize>>,a:usize)->Option<Placement>{
    if read.len()<2*a+1||read.len()!=prep.lowq.len().saturating_sub(1){return None;}
    let (kmers,low)=(&prep.kmers,&prep.lowq);let mut start=None;let mut calls=HashMap::new();
    let limit=read.len().saturating_sub(2*a+1);
    for i in 0..=limit{
        if !valid_window(low,i,i+2*a+1){continue;}
        if i+a+1>=kmers.len(){continue;}
        let (left,right)=(kmers[i],kmers[i+a+1]);if left==INVALID||right==INVALID{continue;}
        let key=((left as u128)<<(2*a))|right as u128;
        let Some(Some(pos))=index.get(&key)else{continue;};
        let placement=*pos as isize-(i+a) as isize;
        if placement<0||start.is_some_and(|s|s!=placement){return None;}
        start=Some(placement);let base=read[i+a];
        calls.entry(*pos).and_modify(|b|if *b!=base{*b=b'N';}).or_insert(base);
    }
    calls.retain(|_,base|*base!=b'N');if calls.len()<2{return None;}
    let start=start?;Some(Placement{start,end:start+read.len() as isize,calls})
}
pub(super) fn original_pair_calls_cached_borrowed(pair_reads:&[&Vec<u8>],pair_prep:&[&ReadPrep],index:&HashMap<u128,Option<usize>>,a:usize)->HashMap<usize,u8>{
    if pair_reads.len()!=4||pair_prep.len()!=4{return HashMap::new();}
    let oriented=[locate_cached(pair_reads[0],pair_prep[0],index,a),locate_cached(pair_reads[1],pair_prep[1],index,a),
                  locate_cached(pair_reads[2],pair_prep[2],index,a),locate_cached(pair_reads[3],pair_prep[3],index,a)];
    let (a_place,b_place)=match &oriented{
        [Some(r1),None,None,Some(r2)] if r1.start<=r2.start=>(r1,r2),
        [None,Some(r1),Some(r2),None] if r2.start<=r1.start=>(r1,r2),
        _=>return HashMap::new(),
    };
    let first=a_place.start.min(b_place.start);let last=a_place.end.max(b_place.end);
    let longest=pair_reads.iter().map(|r|r.len()).max().unwrap_or(0);
    let max_span=longest.saturating_mul(2).saturating_add(200).min(750);
    if (last-first) as usize>max_span{return HashMap::new();}
    let mut calls=a_place.calls.clone();
    for (&pos,&base) in &b_place.calls{calls.entry(pos).and_modify(|existing|{if *existing!=base{*existing=b'N';}}).or_insert(base);}
    calls.retain(|_,base|*base!=b'N');calls
}
pub(super) fn original_pair_calls_cached(pair_reads:&[Vec<u8>],pair_prep:&[ReadPrep],index:&HashMap<u128,Option<usize>>,a:usize)->HashMap<usize,u8>{
    if pair_reads.len()!=4||pair_prep.len()!=4{return HashMap::new();}
    let reads_ref=[&pair_reads[0],&pair_reads[1],&pair_reads[2],&pair_reads[3]];
    let prep_ref=[&pair_prep[0],&pair_prep[1],&pair_prep[2],&pair_prep[3]];
    original_pair_calls_cached_borrowed(&reads_ref,&prep_ref,index,a)
}
