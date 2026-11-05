use std::collections::{HashMap,HashSet};

// "Support" is read-record evidence, not independent physical molecules.
// A 31-mer count samples every third original-read window (first 50k pairs).
pub(crate) fn supported_snv_alternative(
    seq:&[u8], support:usize, kept:&[Vec<u8>],
    supports:&[usize], sampled:&HashMap<u64,u32>,
    canonical:fn(&[u8])->Option<u64>,
)->bool {
    if seq.len()<128 || support<50 || sampled.is_empty() { return false; }
    kept.iter().zip(supports).any(|(old,&prior)| {
        if old.len()!=seq.len() || support.saturating_mul(4)<prior {
            return false;
        }
        let mut variant=None;
        for (i,(&a,&b)) in seq.iter().zip(old).enumerate() {
            if a!=b {
                if variant.is_some() { return false; }
                variant=Some(i);
            }
        }
        let Some(pos)=variant else { return false; };
        if pos<31 || pos+31>=seq.len(){ return false; }
        let original=old.windows(31).filter_map(canonical).collect::<HashSet<_>>();
        seq[pos-30..pos+31].windows(31).filter_map(canonical).filter(|key| {
            !original.contains(key) && sampled.get(key).copied().unwrap_or(0)>=5
        }).take(3).count()>=3
    })
}

#[test] fn unsupported_single_base_errors_are_not_preserved() {
    let original=vec![b'A';200];
    let mut changed=original.clone(); changed[100]=b'C';
    let mut counts=HashMap::new();counts.insert(42,100);
    let encode=|s:&[u8]| Some(s.iter().map(|b|*b as u64).sum::<u64>());
    assert!(!supported_snv_alternative(&changed,1,&[original.clone()],&[200],&counts,encode));
    assert!(!supported_snv_alternative(&changed,150,&[original],&[200],&HashMap::new(),encode));
}

// Variant preservation must never evict a different contig at the caller's cap.
pub(crate) fn append_only_to_spare_slots(
    contigs:&mut Vec<Vec<u8>>, variants:Vec<Vec<u8>>, cap:usize,
    covered:&mut HashSet<u64>, canonical:fn(&[u8])->Option<u64>,
)->usize {
    let mut added=0; for seq in variants.into_iter().take((cap/8).clamp(1,16)) {
        if contigs.len()>=cap { break; }
        let novel=seq.windows(31).filter_map(canonical)
            .filter(|key|!covered.contains(key)).collect::<HashSet<_>>();
        if !novel.is_empty() && !contigs.contains(&seq) {
            covered.extend(novel); contigs.push(seq); added+=1;
        }
    }
    added
}
