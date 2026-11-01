use super::rescue_rank::append_preserving_diversity;
#[test] fn spare_rescue_slot_preserves_every_original_path() {
    let originals=vec![vec![b'A';80],vec![b'C';80]];
    let mut output=originals.clone();
    assert!(append_preserving_diversity(&mut output,vec![b'G';1200],3,1));
    assert_eq!(&output[..originals.len()],originals.as_slice());
    assert_eq!(output.len(),3);
}

#[test] fn explicit_sixteen_contig_cap_is_never_exceeded() {
    let originals=(0..16u64).map(|i| {
        let mut state=0x9e37_79b9_7f4a_7c15u64.wrapping_mul(i+1);
        (0..80).map(|_| {
            state^=state<<13;state^=state>>7;state^=state<<17;
            b"ACGT"[(state&3) as usize]
        }).collect::<Vec<_>>()
    }).collect::<Vec<_>>();
    let mut output=originals.clone();
    assert!(!append_preserving_diversity(&mut output,vec![b'G';1200],16,0));
    assert_eq!(output,originals);
}

#[test] fn same_31mers_do_not_justify_losing_a_longer_path() {
    let mut contigs=vec![vec![b'A';80],vec![b'A';120],vec![b'C';90]];
    let before=contigs.clone();
    assert!(!append_preserving_diversity(&mut contigs,b"ACGT".repeat(300),3,1));
    assert_eq!(contigs,before);
}
#[test] fn rescue_can_replace_an_exact_path_it_contains() {
    let mut contigs=vec![vec![b'C';90],vec![b'A';80]];
    let mut rescue=vec![b'G';1000];
    rescue.extend(vec![b'A';80]);
    assert!(append_preserving_diversity(&mut contigs,rescue.clone(),2,1));
    assert_eq!(contigs[1],rescue);
}
