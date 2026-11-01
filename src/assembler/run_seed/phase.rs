use std::collections::HashSet;
use super::rc;

// Exact orientation-neutral 101-mers preserve linkage beyond 31-mer coverage.
pub(super) fn phased_windows(seq:&[u8])->HashSet<Vec<u8>> {
    seq.windows(101).map(|window| {
        let reverse=rc(window);
        if window<=reverse.as_slice() {window.to_vec()} else {reverse}
    }).collect()
}

pub(super) fn retains_phasing(sets:&[HashSet<Vec<u8>>], rescue:&HashSet<Vec<u8>>,
                              removed:usize)->bool {
    let mut others=rescue.clone();
    for (i,kmers) in sets.iter().enumerate() {
        if i!=removed {others.extend(kmers.iter().cloned());}
    }
    sets[removed].is_subset(&others)
}
