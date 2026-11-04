use std::collections::VecDeque;
use super::{collect::observations,detect::incompatible_link};
pub(crate) fn split_unsupported_contigs(contigs: Vec<Vec<u8>>,
    reads: &[Vec<u8>], max: usize) -> Vec<Vec<u8>> {
    let mut queue=VecDeque::from(contigs);
    let mut output=Vec::new();
    while let Some(seq)=queue.pop_front() {
        let calls=observations(&seq,reads,25);
        if let Some((p,q,bridges))=incompatible_link(&seq,reads,&calls) {
            let cut=(p+q)/2;
            eprintln!("EXPERIMENTAL_PHASE_GUARD unsupported join {p}..{q}, {bridges} distinct observed pair sequences");
            if cut>=31 && seq.len()-cut>=31 && output.len()+queue.len()+2<=max {
                queue.push_front(seq[cut..].to_vec());
                queue.push_front(seq[..cut].to_vec());
            } else {
                eprintln!("EXPERIMENTAL_PHASE_GUARD withholding unsplittable contig");
            }
        } else if output.len()<max {
            output.push(seq);
        }
    }
    output
}
