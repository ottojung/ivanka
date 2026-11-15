use super::{Hits, K};
use std::collections::HashMap;

/// Only a consistent read-to-contig offset can establish a mate anchor.
pub(crate) fn anchor(read: &[u8], hits: &Hits) -> Option<usize> {
    if read.len() < K {
        return None;
    }
    let mut paths = HashMap::<(usize, bool, isize), (usize, usize, usize)>::new();
    for pos in (0..=read.len() - K).step_by(2) {
        if let Some(loci) = hits.get(&read[pos..pos + K]) {
            for &(i, locus) in loci {
                let forward = locus as isize - pos as isize;
                let reverse = (locus + pos) as isize;
                for (rev, offset) in [(false, forward), (true, reverse)] {
                    let record = paths.entry((i, rev, offset)).or_insert((0, pos, pos));
                    record.0 += 1;
                    record.1 = record.1.min(pos);
                    record.2 = record.2.max(pos);
                }
            }
        }
    }
    // A single unique contig is not enough: multiple qualifying offset
    // paths within that contig (e.g. across a repeat) are ambiguous and
    // must not anchor mate evidence. Require exactly one qualifying path.
    let qualifying: Vec<usize> = paths
        .into_iter()
        .filter_map(|((i, _, _), (count, low, high))| (count >= 2 && high - low >= 20).then_some(i))
        .collect();
    (qualifying.len() == 1).then(|| qualifying[0])
}
