use super::{HashMap, K};
use std::collections::HashSet;

/// Look for a common technical suffix in *both* mates, not a known adapter.
pub(super) fn common(sequences: &[Vec<u8>]) -> Option<Vec<u8>> {
    let sampled = sequences.chunks_exact(4).take(2000).collect::<Vec<_>>();
    if sampled.len() < 100 {
        return None;
    }
    for width in (12..=24).rev() {
        let mut frequencies = HashMap::<Vec<u8>, [usize; 2]>::new();
        for pair in &sampled {
            for (side, index) in [(0, 0), (1, 2)] {
                let read = &pair[index];
                if read.len() >= width + K {
                    let entry = frequencies
                        .entry(read[read.len() - width..].to_vec())
                        .or_default();
                    entry[side] += 1;
                }
            }
        }
        for (suffix, counts) in frequencies {
            if counts.iter().any(|&n| n * 10 < sampled.len() * 9) {
                continue;
            }
            let mut preceding = HashSet::new();
            for pair in &sampled {
                for &index in &[0, 2] {
                    let read = &pair[index];
                    if read.len() >= width + 16 && read.ends_with(&suffix) {
                        preceding.insert(&read[read.len() - width - 16..read.len() - width]);
                    }
                }
            }
            if preceding.len() >= 64 {
                return Some(suffix);
            }
        }
    }
    None
}
