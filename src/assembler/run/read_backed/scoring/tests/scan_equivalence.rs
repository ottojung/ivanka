//! Frozen per-locus oracle used only in tests. It mirrors the original
//! decision for each locus and proves the one-pass scan is equivalent even
//! when one 31-mer maps to many loci or to several candidates.

use super::super::super::super::K;
use super::super::super::index::Hits;
use super::super::scan::{pair_loci, Loci};
use std::collections::HashMap;

fn key(base: u8) -> [u8; K] {
    let mut word = [b'A'; K];
    word[K - 1] = base;
    word
}

fn legacy(hits: &Hits, first: &[u8], second: &[u8]) -> Loci {
    let (mut matched, mut exclusive) = (HashMap::new(), HashMap::new());
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

#[test]
fn one_pass_matches_per_locus_scan_on_adversarial_hits() {
    let mut hits = Hits::new();
    hits.insert(key(b'A'), (0..8).map(|locus| (1, locus)).collect());
    hits.insert(key(b'C'), (0..8).map(|locus| (locus % 2, locus)).collect());
    hits.insert(key(b'G'), Vec::new());
    hits.insert(key(b'T'), vec![(0, 5)]);
    let keys = [key(b'A'), key(b'C'), key(b'G'), key(b'T')];
    for first in &keys {
        for second in &keys {
            assert_eq!(
                pair_loci(&hits, first, second),
                legacy(&hits, first, second)
            );
        }
    }
    let (matched, exclusive) = pair_loci(&hits, &key(b'A'), &key(b'C'));
    assert_eq!(matched[&1].len(), 8);
    assert_eq!(exclusive[&1].len(), 8);
    assert!(!exclusive.contains_key(&0));
}
