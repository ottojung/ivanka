use super::split::split_unsupported_contigs;
pub(super) fn synthetic(linked: bool) -> (Vec<u8>,Vec<u8>,Vec<Vec<u8>>) {
    let mut seed=13u64;
    let mut candidate=(0..800).map(|_| {
        seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;
        b"ACGT"[(seed&3) as usize]
    }).collect::<Vec<u8>>();
    candidate[200]=b'A';candidate[420]=b'T';
    let mut one=candidate.clone();one[420]=b'C';
    let mut two=candidate.clone();two[200]=b'G';
    let mut reads=Vec::new();
    for i in 0..30 {
        let sequence=if i%2==0 {&one} else {&two};
        let s=140+i;let t=if linked {365+i} else {530+i};
        let a=sequence[s..s+100].to_vec();
        let b=reverse_complement(&sequence[t..t+100]);
        reads.push(a.clone());reads.push(reverse_complement(&a));
        reads.push(b.clone());reads.push(reverse_complement(&b));
    }
    (candidate,one,reads)
}
pub(super) fn reverse_complement(seq: &[u8]) -> Vec<u8> {
    seq.iter().rev().map(|c|match c {
        b'A'=>b'T',b'T'=>b'A',b'C'=>b'G',b'G'=>b'C',_=>b'N'
    }).collect()
}
pub(super) fn qualities(reads: &[Vec<u8>])->Vec<Vec<u8>> {
    reads.iter().map(|r|vec![b'I';r.len()]).collect()
}
pub(super) fn split(seq: Vec<u8>, reads: &[Vec<u8>]) -> Vec<Vec<u8>> {
    split_unsupported_contigs(vec![seq],reads,&qualities(reads),2)
}
