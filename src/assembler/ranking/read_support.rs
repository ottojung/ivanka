//! Reference-blind full-span read support computed only from original reads.
//! No reference, panel, score or downstream choice enters this module.
use super::{rolling_canonical_kmers, HashMap};

// (covered 31-mers, total sampled placement depth, all 31-mers)
type Profile = (usize, u64, usize);

fn profile(seq: &[u8], sampled: &HashMap<u64, u32>) -> Profile {
    let (mut breadth, mut depth, mut valid) = (0usize, 0u64, 0usize);
    for kmer in rolling_canonical_kmers(seq) {
        valid += 1;
        if let Some(&count) = sampled.get(&kmer) {
            breadth += 1;
            depth += u64::from(count);
        }
    }
    (breadth, depth, valid)
}

// Keep distinct read-derived evidence. Only variably-supported candidates that
// cannot displace a dominant full-span path are withheld from the ordinary
// FASTA, so MiCall is not swamped by variants it could mistake for dominant
// haplotypes. Protected read-derived seeds are never removed here.
pub(super) fn admit(
    seqs: Vec<Vec<u8>>,
    protected: usize,
    sampled: &HashMap<u64, u32>,
) -> Vec<Vec<u8>> {
    if sampled.is_empty() || seqs.len() < 2 {
        return seqs;
    }
    let profiles = seqs
        .iter()
        .map(|seq| profile(seq, sampled))
        .collect::<Vec<_>>();
    let dominant = profiles
        .iter()
        .enumerate()
        .max_by(|a, b| a.1 .1.cmp(&b.1 .1).then_with(|| a.1 .0.cmp(&b.1 .0)))
        .map(|(index, _)| index)
        .unwrap_or(0);
    let (breadth, depth, valid) = profiles[dominant];
    // Require overwhelming breadth and depth before withholding anything.
    if breadth * 20 < valid * 17 || depth < 100 {
        return seqs;
    }
    let mut kept = Vec::new();
    for (index, seq) in seqs.into_iter().enumerate() {
        if index >= protected && profiles[index].1.saturating_mul(4) < depth {
            continue;
        }
        kept.push(seq);
    }
    eprintln!(
        "IVANKA_READ_SUPPORT_ADMISSION native {} kept {}",
        profiles.len(),
        kept.len()
    );
    kept
}
