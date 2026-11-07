use std::collections::{HashMap,HashSet};
use super::evidence::{Prep,observations};
pub(super) fn incompatible(seq:&[u8],reads:&[Vec<u8>],preps:&[Prep])->bool{
    let calls=observations(seq,reads,preps);
    let mut counts=HashMap::<usize,[usize;4]>::new();
    for pair in &calls { for (&pos,&b) in pair { let i=match b{b'A'=>0,b'C'=>1,b'G'=>2,b'T'=>3,_=>continue}; counts.entry(pos).or_insert([0;4])[i]+=1; } }

    let mut var=counts.into_iter().filter_map(|(pos,c)|{
        let ri=b"ACGT".iter().position(|&b|b==seq.get(pos).copied().unwrap_or(b'N'))?;
        (c[ri]>=5 && c.iter().sum::<usize>()-c[ri]>=5).then_some(pos) }).collect::<Vec<_>>();
    
    var.sort_unstable(); 
    let longest=reads.iter().map(Vec::len).max().unwrap_or(0);
    let max_span=longest.saturating_mul(2).saturating_add(200).min(750);
    for (i,&p) in var.iter().enumerate(){ for &q in &var[i+1..]{ if q-p>max_span{continue;}
        let mut distinct=HashSet::new(); let mut ref_seen=false;
        for (orig,pair) in reads.chunks_exact(4).zip(&calls){ let (Some(&a),Some(&b))=(pair.get(&p),pair.get(&q)) else {continue;};
            if (a,b)==(seq[p],seq[q]){ref_seen=true;break;} distinct.insert((orig[0].as_slice(),orig[2].as_slice())); }
        if !ref_seen && distinct.len()>=8 { return true; } }}
    false
}
