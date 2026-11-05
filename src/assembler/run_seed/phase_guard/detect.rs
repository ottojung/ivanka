use std::collections::{HashMap,HashSet};
fn variants(seq: &[u8], calls: &[HashMap<usize,u8>]) -> Vec<usize> {
    let mut counts=HashMap::<usize,[usize;4]>::new();
    for pair in calls {for (&pos,&b) in pair {
        let i=match b {b'A'=>0,b'C'=>1,b'G'=>2,b'T'=>3,_=>continue};
        counts.entry(pos).or_insert([0;4])[i]+=1;
    }}
    let mut result=counts.into_iter().filter_map(|(pos,c)| {
        let ref_index=b"ACGT".iter().position(|&b|b==seq[pos])?;
        (c[ref_index]>=5 && c.iter().sum::<usize>()-c[ref_index]>=5).then_some(pos)
    }).collect::<Vec<_>>();
    result.sort_unstable();result
}
pub(super) fn incompatible_link(seq: &[u8], reads: &[Vec<u8>],
    calls: &[HashMap<usize,u8>]) -> Option<(usize,usize,usize)> {
    let variable=variants(seq,calls);
    // Without measured insert sizes, only screen physically plausible spans.
    // This conservative heuristic is not a certified fragment distribution.
    let longest=reads.iter().map(Vec::len).max().unwrap_or(0);
    let max_span=longest.saturating_mul(2).saturating_add(200).min(750);
    for (i,&p) in variable.iter().enumerate() {
        for &q in &variable[i+1..] {
            if q-p>max_span {continue;}
            let mut distinct=HashSet::new();
            let mut ref_seen=false;
            for (original,pair) in reads.chunks_exact(4).zip(calls) {
                let (Some(&a),Some(&b))=(pair.get(&p),pair.get(&q)) else {continue;};
                if (a,b)==(seq[p],seq[q]) {ref_seen=true;break;}
                distinct.insert((original[0].as_slice(),original[2].as_slice()));
            }
            if !ref_seen && distinct.len()>=8 {return Some((p,q,distinct.len()));}
        }
    }
    None
}
