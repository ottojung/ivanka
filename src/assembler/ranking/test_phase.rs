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

#[test] fn spare_slots_keep_ranked_prefix_and_skip_reverse_complements() {
    use super::phase::append_phased;
    use super::rc;
    let mut rng=0x1234_5678_9abc_def0u64;
    for cap in [1usize,2,3] {
        for _ in 0..128 {
            let mut a=vec![b'A';64];
            for base in &mut a {
                rng^=rng<<13; rng^=rng>>7; rng^=rng<<17;
                *base=b"ACGT"[(rng&3) as usize];
            }
            let mut b=a.clone();
            b.extend_from_slice(b"ACGT");
            let mut retained=vec![a.clone()];
            let deferred=vec![rc(&a),a.clone(),b.clone(),rc(&b)];
            let added=append_phased(&mut retained,deferred,cap);
            assert_eq!(retained[0],a);
            assert_eq!(retained.len(),if cap==1 {1} else {2});
            assert_eq!(added,retained.len()-1);
            if cap>1 {assert_eq!(retained[1],b);}
        }
    }
}
