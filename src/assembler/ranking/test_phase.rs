use super::{select_supported_contigs,rolling_canonical_kmers};
use std::collections::HashSet;
#[test] fn preserves_long_range_phase_when_31mer_unions_agree() {
    let a=[vec![b'A';60],vec![b'C';80],vec![b'A';60],vec![b'G';80],vec![b'A';60]].concat();
    let b=[vec![b'A';60],vec![b'G';80],vec![b'A';60],vec![b'C';80],vec![b'A';60]].concat();
    let ka=rolling_canonical_kmers(&a).collect::<HashSet<_>>();
    let kb=rolling_canonical_kmers(&b).collect::<HashSet<_>>();
    assert_eq!(ka,kb);
    let retained=select_supported_contigs(vec![a.clone(),b.clone()],vec![100,90],16,0);
    assert_eq!(retained,vec![a,b]);
}
