use std::collections::{HashMap, HashSet};

// "Support" is read-record evidence, not independent physical molecules.
// A 31-mer count samples every third original-read window (first 50k pairs).
pub(crate) fn supported_snv_alternative(
    seq: &[u8],
    support: usize,
    kept: &[Vec<u8>],
    supports: &[usize],
    sampled: &HashMap<u64, u32>,
    canonical: fn(&[u8]) -> Option<u64>,
) -> bool {
    if seq.len() < 128 || support < 50 || sampled.is_empty() {
        return false;
    }
    kept.iter().zip(supports).any(|(old, &prior)| {
        if old.len() != seq.len() || support.saturating_mul(4) < prior {
            return false;
        }
        let mut variant = None;
        for (i, (&a, &b)) in seq.iter().zip(old).enumerate() {
            if a != b {
                if variant.is_some() {
                    return false;
                }
                variant = Some(i);
            }
        }
        let Some(pos) = variant else {
            return false;
        };
        if pos < 31 || pos + 31 >= seq.len() {
            return false;
        }
        let original = old
            .windows(31)
            .filter_map(canonical)
            .collect::<HashSet<_>>();
        seq[pos - 30..pos + 31]
            .windows(31)
            .filter_map(canonical)
            .filter(|key| !original.contains(key) && sampled.get(key).copied().unwrap_or(0) >= 5)
            .take(3)
            .count()
            >= 3
    })
}

#[cfg(test)]
mod tests;
