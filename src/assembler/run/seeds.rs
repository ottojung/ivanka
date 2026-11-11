use super::{extend, fasta_seeds, Reads, K};
use std::error::Error;

// Caller-supplied seeds must be derived independently from these sample
// reads. The caller guarantees provenance; Ivanka extends seeds using only
// original reads, never known viral references or alignment scores.// Caller-supplied seeds are permitted only when derived from the sample reads.
pub(super) fn attach(
    seeds_path: Option<&str>,
    reads: &Reads,
    max: usize,
    contigs: &mut Vec<Vec<u8>>,
    supporting_counts: &mut Vec<usize>,
) -> Result<(), Box<dyn Error>> {
    if let Some(seeds_file) = seeds_path {
        let supplied = fasta_seeds(seeds_file)?;
        eprintln!(
            "received {} caller-supplied FASTA seed contigs",
            supplied.len()
        );
        let seed_quota = (max / 3).max(1);
        for seed in supplied
            .into_iter()
            .filter(|seq| seq.len() >= K)
            .take(seed_quota)
        {
            let supplied_len = seed.len();
            let (extended, support) = extend(seed, &reads, 6, 2);
            if extended.len() >= supplied_len
                && !contigs
                    .iter()
                    .any(|c| c.windows(extended.len()).any(|w| w == extended))
            {
                contigs.push(extended);
                supporting_counts.push(support);
            }
        }
    }
    Ok(())
}
