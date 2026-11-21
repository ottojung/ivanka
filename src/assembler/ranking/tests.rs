#[cfg(test)]
use super::read_support::admit;
#[cfg(test)]
use super::{rolling_canonical_kmers, HashMap};

fn template(seed: u64, len: usize) -> Vec<u8> {
    let mut state = seed;
    (0..len)
        .map(|_| {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            match (state >> 33) % 4 {
                0 => b'A',
                1 => b'C',
                2 => b'G',
                _ => b'T',
            }
        })
        .collect()
}

fn sampled(seq: &[u8], depth: u32) -> HashMap<u64, u32> {
    rolling_canonical_kmers(seq)
        .map(|key| (key, depth))
        .collect()
}

#[test]
fn weak_variant_is_withheld_but_protected_seed_survives() {
    let strong = template(11, 400);
    let weak = template(23, 300);
    let seed = template(37, 300);
    let counts = sampled(&strong, 200);
    let kept = admit(vec![strong.clone(), seed.clone(), weak], 2, &counts);
    assert_eq!(kept, vec![strong, seed]);
}

#[test]
fn no_sampled_evidence_changes_nothing() {
    let seq = template(11, 400);
    assert_eq!(admit(vec![seq.clone()], 0, &HashMap::new()), vec![seq]);
}
