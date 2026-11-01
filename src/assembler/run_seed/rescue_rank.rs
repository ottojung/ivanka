use super::phase::{phased_windows,retains_phasing};
use std::collections::HashSet;
use super::{canonical_kmer,K};

// Add a rescue only if no protected seed or unique 31-mer is displaced.
// An exact k-mer cover is conservative; it is not a haplotype guarantee.
pub(crate) fn append_preserving_diversity(contigs:&mut Vec<Vec<u8>>,
    rescue:Vec<u8>,cap:usize,protected:usize)->bool {
    if cap==0 || rescue.len()<K {return false;}
    if contigs.len()<cap {contigs.push(rescue);return true;}
    let cover=|seq:&[u8]| -> HashSet<u64> {
        seq.windows(K).filter_map(canonical_kmer).collect()
    };
    let sets=contigs.iter().map(|s|cover(s)).collect::<Vec<_>>();
    let rescue_set=cover(&rescue);
    let (phased,rescue_phased)=(contigs.iter().map(|s|phased_windows(s)).collect::<Vec<_>>(),phased_windows(&rescue));
    let removable=(protected..contigs.len()).filter(|&i| {
        let mut others=rescue_set.clone();
        for (j,kmers) in sets.iter().enumerate() {
            if i!=j {others.extend(kmers.iter().copied());}
        }
        sets[i].is_subset(&others) && retains_phasing(&phased,&rescue_phased,i)
    }).min_by_key(|&i|contigs[i].len());
    if let Some(i)=removable {
        contigs[i]=rescue;
        eprintln!("Ivanka rescue retained every original canonical 31-mer");
        true
    } else {
        eprintln!("Ivanka rescue withheld: no diversity-preserving slot");
        false
    }
}
#[test] fn rescue_replaces_only_redundant_unprotected_contig() {
    let mut old=vec![vec![b'A';80],vec![b'A';100],vec![b'C';90]];
    let rescue=vec![b'G';1200];
    assert!(append_preserving_diversity(&mut old,rescue,3,1));
    assert_eq!(old[0],vec![b'A';80]);
    assert_eq!(old.iter().map(Vec::len).max(),Some(1200));
}
#[test] fn distinct_contigs_are_never_displaced() {
    let mut old=vec![vec![b'A';80],vec![b'C';80]];
    assert!(!append_preserving_diversity(&mut old,b"ACGT".repeat(300),2,0));
    assert_eq!(old.len(),2);
}
#[test] fn accepted_rescue_preserves_canonical_kmer_union() {
    let mut old=vec![vec![b'A';80],vec![b'A';100],vec![b'C';90]];
    let kmers=|v:&[Vec<u8>]| -> HashSet<u64> {
        v.iter().flat_map(|s|s.windows(K).filter_map(canonical_kmer)).collect()
    };
    let before=kmers(&old);
    assert!(append_preserving_diversity(&mut old,vec![b'G';1200],3,1));
    assert!(before.is_subset(&kmers(&old)));
}
