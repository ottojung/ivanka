use super::snv::append_only_to_spare_slots;
use std::collections::HashSet;

fn mark(w:&[u8])->Option<u64> {Some(w[0] as u64)}

#[test] fn no_unique_contig_can_be_evicted_at_cap() {
    let original=vec![vec![b'A';90],vec![b'C';90]];
    let mut capped=original.clone(); let alternative=vec![vec![b'G';90]];
    let mut covered=HashSet::from([b'A' as u64,b'C' as u64]);
    assert_eq!(append_only_to_spare_slots(&mut capped,alternative.clone(),2,&mut covered,mark),0);
    assert_eq!(capped,original);
    assert_eq!(append_only_to_spare_slots(&mut capped,alternative,3,&mut covered,mark),1);
    assert_eq!(capped.len(),3);
}
#[test] fn no_kmer_novelty_means_no_spurious_extra_remap_contig() {
    let mut existing=vec![vec![b'A';90]];
    let mut covered=HashSet::from([b'A' as u64]);
    assert_eq!(append_only_to_spare_slots(&mut existing,vec![vec![b'A';91]],1000,&mut covered,mark),0);
    assert_eq!(existing.len(),1);
}
#[test] fn budget_prevents_spare_slot_alternatives_from_flooding_micall() {
    let mut existing=Vec::new(); let mut covered=HashSet::new();
    let variations=(0..100).map(|i| vec![i as u8;100]).collect::<Vec<_>>();
    assert_eq!(append_only_to_spare_slots(&mut existing,variations,1000,&mut covered,mark),16);
    assert_eq!(existing.len(),16);
}
