use super::Evidence;

pub(crate) fn vet_rescue_with(ev: &Evidence, seq: Vec<u8>, reads: &[Vec<u8>]) -> Option<Vec<u8>> {
    let (mut kept, _) = super::reject_with(ev, vec![seq], vec![0], reads, 0);
    kept.pop()
}

#[cfg(test)]
pub(crate) fn reject_unsupported_recombinants(
    seqs: Vec<Vec<u8>>,
    counts: Vec<usize>,
    reads: &[Vec<u8>],
    quals: &[Vec<u8>],
    protected: usize,
) -> (Vec<Vec<u8>>, Vec<usize>) {
    let ev = super::prepare(reads, quals);
    super::reject_with(&ev, seqs, counts, reads, protected)
}

#[cfg(test)]
pub(crate) fn vet_rescue(seq: Vec<u8>, reads: &[Vec<u8>], quals: &[Vec<u8>]) -> Option<Vec<u8>> {
    let ev = super::prepare(reads, quals);
    vet_rescue_with(&ev, seq, reads)
}
