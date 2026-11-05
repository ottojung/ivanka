use std::collections::{HashMap, HashSet};

pub(super) struct Observation {
    pub(super) parent:usize, pub(super) pos:usize,
    pub(super) original:u8, pub(super) alternate:u8,
    pub(super) length:usize, pub(super) support:usize,
    pub(super) kmer_witnesses:usize, pub(super) context:String,
}

pub(super) fn local_variants(
    rejected:&[(Vec<u8>,usize)], output:&[Vec<u8>],
    sampled:&HashMap<u64,u32>, canonical:fn(&[u8])->Option<u64>,
)->Vec<Observation> {
    let represented=output.iter().flat_map(|s|s.windows(31).filter_map(canonical))
        .collect::<HashSet<_>>();
    let mut result=Vec::new();
    let mut observed=HashSet::new();
    for (seq,&support) in rejected.iter().map(|(s,n)|(s,n)) {
        if result.len()>=16 {break;}
        for (index,parent) in output.iter().enumerate() {
            if parent.len()!=seq.len(){continue;}
            let diffs=seq.iter().zip(parent).enumerate()
                .filter(|(_, (a,b))|a!=b).map(|(i,_)|i).take(2).collect::<Vec<_>>();
            if diffs.len()!=1 {continue;}
            let pos=diffs[0];
            if pos<31 || pos+31>=seq.len(){continue;}
            let novel=seq[pos-30..pos+31].windows(31).filter_map(canonical)
                .filter(|k|!represented.contains(k) && sampled.get(k).copied().unwrap_or(0)>=5)
                .collect::<HashSet<_>>();
            if novel.len()<3 {continue;}
            let context=String::from_utf8_lossy(&seq[pos-30..pos+31]).into_owned();
            if !observed.insert((index,pos,seq[pos])) {break;}
            result.push(Observation{parent:index+1,pos,original:parent[pos],
                alternate:seq[pos],length:seq.len(),support,
                kmer_witnesses:novel.len(),context});
            break;
        }
    }
    result
}
