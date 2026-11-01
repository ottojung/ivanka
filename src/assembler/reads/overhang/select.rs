// Keep a single contribution per FASTQ record. Repetitive anchors can yield
// several exact placements; the longest overlap supplies the strongest phase.
pub(super) fn record_best(original:u32,overlap:usize,suffix:&[u8],
    used:&mut [(u32,u32)],ext:&mut Vec<Vec<u8>>,ids:&mut Vec<u32>) {
    let entry=&mut used[original as usize];
    if entry.0!=0 {
        ext[(entry.0-1) as usize]=suffix.to_vec();
    } else {
        entry.0=(ext.len()+1) as u32;
        ext.push(suffix.to_vec());
        ids.push(original);
    }
    entry.1=overlap as u32;
}
