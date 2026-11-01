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

pub(crate) fn trace_extension_stop(len:usize,right:&[Vec<u8>],left:&[Vec<u8>]) {
    if std::env::var_os("IVANKA_TRACE_EXTENSIONS").is_some() {
        eprintln!("EXTENSION_STOP length={} right_reads={} right_bases={:?} left_reads={} left_bases={:?}",
            len,right.len(),summarize(right),left.len(),summarize(left));
    }
}
