use super::{HashMap, HashSet, Hits, K};

/// Loci per candidate supported by one original pair: all hits, then the
/// subset whose oriented 31-mer occurs in no other candidate.
///
/// Both mates are scanned in their given orientation. The index already
/// carries both strands of every contig, so a hit is read-derived evidence
/// only: no truth, reference panel or evaluator output reaches this path.
/// The original pair remains the voting unit, which keeps provenance intact
/// and makes selection depend solely on deterministic read evidence.
pub(super) type Loci = (
    HashMap<usize, HashSet<usize>>,
    HashMap<usize, HashSet<usize>>,
);

pub(super) fn pair_loci(hits: &Hits, first: &[u8], second: &[u8]) -> Loci {
    let mut matched: HashMap<usize, HashSet<usize>> = HashMap::new();
    let mut exclusive: HashMap<usize, HashSet<usize>> = HashMap::new();
    for read in [first, second] {
        if read.len() < K {
            continue;
        }
        for pos in (0..=read.len() - K).step_by(2) {
            if let Some(locations) = hits.get(&read[pos..pos + K]) {
                for &(candidate, locus) in locations {
                    matched.entry(candidate).or_default().insert(locus);
                    if locations.iter().all(|&(other, _)| other == candidate) {
                        exclusive.entry(candidate).or_default().insert(locus);
                    }
                }
            }
        }
    }
    (matched, exclusive)
}
