pub(crate) fn summarize(overhangs:&[Vec<u8>]) -> [usize;4] {
    let mut counts=[0usize;
    4];
    for o in overhangs {
        if let Some(&base)=o.first() {
            match base {b'A'=>counts[0]+=1,b'C'=>counts[1]+=1,
                b'G'=>counts[2]+=1,b'T'=>counts[3]+=1,_=>{}}
        }
    }
    counts
}
