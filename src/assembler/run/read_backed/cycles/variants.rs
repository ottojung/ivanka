//! Represent alternative cycle openings, not different asserted haplotypes.
use super::Entry;

fn rotated(sequence: &[u8], cycle: usize, origin: usize) -> Vec<u8> {
    let mut result = Vec::with_capacity(sequence.len());
    for position in 0..sequence.len() {
        result.push(sequence[(origin + position) % cycle]);
    }
    result
}

fn reverse(sequence: &[u8]) -> Vec<u8> {
    sequence.iter().rev().map(|base| match base {
        b'A' => b'T', b'T' => b'A', b'G' => b'C', b'C' => b'G',
        _ => *base,
    }).collect()
}

pub(crate) fn build(header: &str, sequence: &[u8], overlap: usize,
                    start: usize, end: usize) -> Vec<Entry> {
    let cycle = sequence.len() - overlap;
    let original = rotated(sequence, cycle, end % cycle);
    let reversed = reverse(sequence);
    let reverse_origin = (sequence.len() - 100 - start) % cycle;
    let alternate = rotated(&reversed, cycle, reverse_origin);
    if original == alternate {
        return vec![(format!("{header}_opening1"), original)];
    }
    vec![(format!("{header}_opening1"), original),
         (format!("{header}_opening2"), alternate)]
}
