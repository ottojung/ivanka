use super::{decode, extend, HashSet, Reads};

pub(super) fn assemble_primary(
    candidates: Vec<(u64, u32)>,
    reads: &Reads,
    contigs: &mut Vec<Vec<u8>>,
    supporting_counts: &mut Vec<usize>,
    primary_limit: usize,
) -> HashSet<u64> {
    let mut attempted = 0usize;
    let mut attempted_seeds = HashSet::new();
    for (seed, count) in candidates {
        if attempted >= primary_limit || count < 15 {
            break;
        }
        let seedseq = decode(seed);
        // A k-mer can occur in both a dominant strain and a distinct supported
        // haplotype. Keep independent seed starts rather than treating a
        // previously traversed 31-mer as proof of redundant full contigs.
        // The bounded attempt budget and final read-support/novelty ranking
        // still cap work and reported output.
        attempted += 1;
        attempted_seeds.insert(seed);
        let (seq, support) = extend(seedseq, &reads, 4, 1);
        if !seq.is_empty() {
            eprintln!(
                "candidate {} coverage {} produced {} nt",
                attempted,
                count,
                seq.len()
            );
            // Do not merge contigs, merely suppress exact contained duplicates.
            if !contigs
                .iter()
                .any(|c| c.windows(seq.len()).any(|w| w == seq))
            {
                contigs.push(seq);
                supporting_counts.push(support);
            }
        }
        if attempted % 20 == 0 {
            eprintln!("tried {} seeds, accepted {}", attempted, contigs.len());
        }
    }
    // A second bounded, high-evidence search complements balanced-depth
    // exploration. We deliberately revisit seeds represented in an earlier
    // contig: a different internal anchor can extend through a difficult
    // junction, while final support/novelty selection still de-duplicates.
    attempted_seeds
}
