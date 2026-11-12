use super::{Hits, Key, K};

fn reverse_complement(kmer: &Key) -> Key {
    let mut reverse = [0u8; K];
    for (index, base) in kmer.iter().rev().enumerate() {
        reverse[index] = match base {
            b'A' => b'T',
            b'C' => b'G',
            b'G' => b'C',
            _ => b'A',
        };
    }
    reverse
}

/// Repeats with more than eight oriented placements cannot anchor evidence.
pub(crate) fn build(contigs: &[Vec<u8>]) -> Hits {
    let mut index = Hits::new();
    for (candidate, sequence) in contigs.iter().enumerate() {
        for (position, window) in sequence.windows(K).enumerate() {
            if !window
                .iter()
                .all(|base| matches!(base, b'A' | b'C' | b'G' | b'T'))
            {
                continue;
            }
            let key: Key = window.try_into().expect("fixed-length window");
            index.entry(key).or_default().push((candidate, position));
            let reverse = reverse_complement(&key);
            index
                .entry(reverse)
                .or_default()
                .push((candidate, position));
        }
    }
    index.retain(|_, loci| loci.len() <= 8);
    index
}
