use super::verdict;
use super::Evidence;

pub(crate) fn reject_with(
    ev: &Evidence,
    seqs: Vec<Vec<u8>>,
    counts: Vec<usize>,
    reads: &[Vec<u8>],
    protected: usize,
) -> (Vec<Vec<u8>>, Vec<usize>) {
    let verdicts = verdict::evaluate(ev, &seqs, reads, protected);
    let mut kept_s = Vec::new();
    let mut kept_c = Vec::new();
    let mut dropped = 0usize;
    for (index, (seq, count)) in seqs.into_iter().zip(counts).enumerate() {
        // MiCall-supplied seeds stay protected: their admission belongs to the
        // original-pair-preserving MiCall front, not to this de novo veto.
        let bad = verdicts[index];
        if bad {
            dropped += 1;
            eprintln!(
                "IVANKA_PHASE_GUARD withheld unsupported recombinant candidate ({} nt, support {})",
                seq.len(),
                count
            );
        } else {
            kept_s.push(seq);
            kept_c.push(count);
        }
    }
    if dropped > 0 {
        eprintln!(
            "IVANKA_PHASE_GUARD filtered {} candidate(s) contradicted by direct original-pair evidence",
            dropped
        );
    }
    (kept_s, kept_c)
}
