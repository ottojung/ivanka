use super::{canonical_kmer, K};
use std::collections::HashSet;
pub(super) fn oracle(v: &mut Vec<Vec<u8>>, rescue: Vec<u8>, cap: usize, protected: usize) -> bool {
    if cap == 0 || rescue.len() < K {
        return false;
    }
    if v.len() < cap {
        v.push(rescue);
        return true;
    }
    let cover = |s: &[u8]| -> HashSet<u64> { s.windows(K).filter_map(canonical_kmer).collect() };
    let sets = v.iter().map(|s| cover(s)).collect::<Vec<_>>();
    let rs = cover(&rescue);
    let idx = (protected..v.len())
        .filter(|&i| {
            let mut other = rs.clone();
            for (j, ks) in sets.iter().enumerate() {
                if i != j {
                    other.extend(ks.iter().copied());
                }
            }
            sets[i].is_subset(&other)
        })
        .min_by_key(|&i| v[i].len());
    if let Some(i) = idx {
        v[i] = rescue;
        true
    } else {
        false
    }
}
