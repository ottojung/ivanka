use std::collections::HashMap;

// Equal attention to solid k-mers at different sequencing depths prevents
// oversampled regions monopolizing the bounded seed-extension budget.
// This is reference-free and never removes or consumes any reads.
pub(super) fn balanced_seed_candidates(counts:&HashMap<u64,u32>) -> Vec<(u64,u32)> {
    let mut buckets=vec![Vec::<(u64,u32)>::new();32];
    for (&key,&count) in counts {
        if count < 15 {continue;}
        let level=(31-count.leading_zeros()) as usize;
        buckets[level].push((key,count));
    }
    let mut longest=0usize;
    for bucket in &mut buckets {
        bucket.sort_unstable_by_key(|&(key,_)| key.wrapping_mul(0x9e3779b97f4a7c15));
        longest=longest.max(bucket.len());
    }
    let mut selected=Vec::with_capacity(buckets.iter().map(Vec::len).sum());
    for rank in 0..longest {
        for bucket in buckets.iter().rev() {
            if let Some(&seed)=bucket.get(rank) {selected.push(seed);}
        }
    }
    selected
}
