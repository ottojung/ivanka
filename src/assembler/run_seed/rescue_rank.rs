use super::rescue_path::contains_or_rc;
#[cfg(test)] use std::collections::HashSet;
#[cfg(test)] use super::canonical_kmer;
#[cfg(test)] use super::K;

// A full source path must survive, not just its constituent 31-mers:
// different phased haplotypes can have the same union of short k-mers.
pub(crate) fn append_preserving_diversity(contigs:&mut Vec<Vec<u8>>,
    rescue:Vec<u8>,cap:usize,protected:usize)->bool {
    if cap==0 || rescue.len()<super::K {return false;}
    if contigs.len()<cap {contigs.push(rescue);return true;}
    let removable=(protected..contigs.len()).filter(|&i| {
        contains_or_rc(&rescue,&contigs[i]) ||
        contigs.iter().enumerate().any(|(j,c)|j!=i && contains_or_rc(c,&contigs[i]))
    }).min_by_key(|&i|contigs[i].len());
    if let Some(i)=removable {
        contigs[i]=rescue;
        eprintln!("Ivanka rescue retained every original contig path");
        true
    } else {
        eprintln!("Ivanka rescue withheld: no path-preserving slot");
        false
    }
}
#[test] fn rescue_replaces_only_redundant_unprotected_contig() {
    let mut old=vec![vec![b'A';120],vec![b'A';80],vec![b'C';90]];
    let rescue=vec![b'G';1200];
    assert!(append_preserving_diversity(&mut old,rescue,3,1));
    assert_eq!(old[0],vec![b'A';120]);
    assert_eq!(old.iter().map(Vec::len).max(),Some(1200));
}
#[test] fn distinct_contigs_are_never_displaced() {
    let mut old=vec![vec![b'A';80],vec![b'C';80]];
    assert!(!append_preserving_diversity(&mut old,b"ACGT".repeat(300),2,0));
    assert_eq!(old.len(),2);
}
#[test] fn accepted_rescue_preserves_canonical_kmer_union() {
    let mut old=vec![vec![b'A';120],vec![b'A';80],vec![b'C';90]];
    let kmers=|v:&[Vec<u8>]| -> HashSet<u64> {
        v.iter().flat_map(|s|s.windows(K).filter_map(canonical_kmer)).collect()
    };
    let before=kmers(&old);
    assert!(append_preserving_diversity(&mut old,vec![b'G';1200],3,1));
    assert!(before.is_subset(&kmers(&old)));
}
