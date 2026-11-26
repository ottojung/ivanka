use super::{rolling, Hits};

/// Repeats with more than eight oriented placements cannot anchor evidence.
/// K is odd, so no window equals its reverse complement: one canonical insert
/// per window preserves the byte index's two oriented loci, hence its retain
/// threshold and every lookup's locus multiset.
pub(crate) fn build(contigs: &[Vec<u8>]) -> Hits {
    let mut index = Hits::new();
    for (candidate, sequence) in contigs.iter().enumerate() {
        for (position, key) in rolling(sequence) {
            index.entry(key).or_default().push((candidate, position));
        }
    }
    index.retain(|_, loci| loci.len() <= 8);
    index
}
