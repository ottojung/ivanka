use super::rescue_rank::append_preserving_diversity;
#[test] fn spare_rescue_slot_preserves_every_original_path() {
    let originals=vec![vec![b'A';80],vec![b'C';80]];
    let mut output=originals.clone();
    assert!(append_preserving_diversity(&mut output,vec![b'G';1200],3,1));
    assert_eq!(&output[..originals.len()],originals.as_slice());
    assert_eq!(output.len(),3);
}
