//! Differential control: primary evidence must match the pre-change algorithm.
mod legacy;
use super::{index, index::Hits, paired, reverse_complement, scoring, sequence, Reads, K};
use legacy::legacy;

#[test]
fn depth_and_pair_evidence_match_legacy_count_on_adversarial_reads() {
    let mut first = sequence(83, 200);
    let duplicated = first[20..80].to_vec();
    first.extend_from_slice(&sequence(101, 40));
    first.extend_from_slice(&duplicated);
    first.extend_from_slice(&sequence(103, 40));
    let contigs = vec![first, sequence(97, 260)];
    let hits = index::build(&contigs);
    let mates = vec![
        (contigs[0][20..65].to_vec(), sequence(109, 45)),
        (
            contigs[1][30..75].to_vec(),
            reverse_complement(&contigs[1][160..205]),
        ),
        (vec![b'N'; 12], contigs[0][120..165].to_vec()),
    ];
    let reads = paired(&mates);
    let fresh = scoring::count(&contigs, &reads, &hits);
    let (depth, pairs) = legacy(&contigs, &reads, &hits);
    assert_eq!(fresh.depth, depth);
    assert_eq!(fresh.pairs, pairs);
    let coverage = depth
        .iter()
        .map(|d| d.iter().filter(|&&v| v >= 3).count())
        .collect::<Vec<_>>();
    assert_eq!(fresh.coverage, coverage);
}
