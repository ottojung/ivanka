pub(crate) fn choose_extension(overhangs:&[Vec<u8>], min_cov:usize, min_ratio:usize, max_extension:usize)->Vec<u8>{
    let mut out=Vec::new();
    let mut remaining=(0..overhangs.len()).collect::<Vec<_>>();
    for i in 0..max_extension {
        let mut counts=[0usize;
        4];
        for &x in &remaining {
            if i<overhangs[x].len() {
                match overhangs[x][i] {b'A'=>counts[0]+=1,b'C'=>counts[1]+=1,b'G'=>counts[2]+=1,b'T'=>counts[3]+=1,_=>{}}
            }
        }
        let mut sorted=counts;
        sorted.sort_unstable_by(|a,b|b.cmp(a));
        if sorted[0]<min_cov || sorted[0]<min_ratio.saturating_mul(sorted[1]) {break;}
        let base=match counts.iter().position(|n|*n==sorted[0]).unwrap(){0=>b'A',1=>b'C',2=>b'G',_=>b'T'};
        out.push(base);
        remaining.retain(|x|overhangs[*x].get(i)==Some(&base));
    }
    out
}
