use std::collections::HashMap;
use super::index::{kmer_codes,INVALID};

struct Placement {start:isize,end:isize,calls:HashMap<usize,u8>}
fn locate(read: &[u8], index: &HashMap<u128,Option<usize>>,
          a: usize) -> Option<Placement> {
    if read.len()<2*a+1 {return None;}
    let kmers=kmer_codes(read,a);
    let mut start=None;
    let mut calls=HashMap::new();
    for i in 0..=read.len()-2*a-1 {
        let (left,right)=(kmers[i],kmers[i+a+1]);
        if left==INVALID || right==INVALID {continue;}
        let key=((left as u128)<<(2*a))|right as u128;
        let Some(Some(pos))=index.get(&key) else {continue;};
        let placement=*pos as isize-(i+a) as isize;
        if placement<0 || start.is_some_and(|s|s!=placement) {return None;}
        start=Some(placement);
        let base=read[i+a];
        calls.entry(*pos).and_modify(|b|if *b!=base {*b=b'N'}).or_insert(base);
    }
    calls.retain(|_,base|*base!=b'N');
    if calls.len()<2 {return None;}
    let start=start?;
    Some(Placement{start,end:start+read.len() as isize,calls})
}
pub(super) fn original_pair_calls(pair: &[Vec<u8>], index:
        &HashMap<u128,Option<usize>>,a:usize) -> HashMap<usize,u8> {
    if pair.len()!=4 {return HashMap::new();}
    let oriented=[locate(&pair[0],index,a),locate(&pair[1],index,a),
                  locate(&pair[2],index,a),locate(&pair[3],index,a)];
    let (a,b) = match &oriented {
        [Some(r1),None,None,Some(r2)] if r1.start<=r2.start=>(r1,r2),
        [None,Some(r1),Some(r2),None] if r2.start<=r1.start=>(r1,r2),
        _=>return HashMap::new(),
    };
    let first=a.start.min(b.start);
    let last=a.end.max(b.end);
    let longest=pair.iter().map(Vec::len).max().unwrap_or(0);
    let max_span=longest.saturating_mul(2).saturating_add(200).min(750);
    if (last-first) as usize>max_span {return HashMap::new();}
    let mut calls=a.calls.clone();
    for (&pos,&base) in &b.calls {
        calls.entry(pos).and_modify(|existing|{
            if *existing!=base {*existing=b'N';}
        }).or_insert(base);
    }
    calls.retain(|_,base|*base!=b'N');
    calls
}
