use super::writer::write_snv_audit;
use super::test_helpers::{example,kmer,output_path};
use std::collections::HashMap;
use std::os::unix::fs::PermissionsExt;

#[test] fn observed_local_variants_are_unphased_separate_evidence() {
    let (base,alt,counts)=example();
    let path=output_path("supported");
    let count=write_snv_audit(&path,&[(alt.clone(),150),(alt.clone(),140)],&[base.clone()],&counts,kmer).unwrap();
    let data=std::fs::read_to_string(&path).unwrap();
    assert_eq!(count,1);
    assert!(data.contains("phasing=unidentified"));
    assert!(data.contains("phred_unchecked=true"));
    assert!(data.contains("independent_dna_molecules=false"));
    assert!(data.contains("1\t300\t150\t"));
    assert!(!data.contains(&String::from_utf8(base).unwrap()));
    assert_eq!(std::fs::metadata(&path).unwrap().permissions().mode()&0o777,0o600);
    assert!(write_snv_audit(&path,&[],&[],&counts,kmer).is_err());
    assert_eq!(data.lines().filter(|line|line.starts_with("1\t300\t150")).count(),1);
    std::fs::remove_file(path).unwrap();
}
#[test] fn unobserved_and_multi_snv_sequences_never_become_nodes() {
    let (base,alt,_)=example();
    let path=output_path("missing");
    let count=write_snv_audit(&path,&[(alt.clone(),150)],&[base.clone()],&HashMap::new(),kmer).unwrap();
    assert_eq!(count,0);std::fs::remove_file(path).unwrap();
    let mut wrong=alt.clone(); wrong[145]=if wrong[145]==b'A'{b'C'}else{b'A'};
    let path=output_path("two");
    let mut counts=HashMap::new();
    for k in wrong.windows(31).filter_map(kmer) {counts.insert(k,10);}
    assert_eq!(write_snv_audit(&path,&[(wrong,150)],&[base],&counts,kmer).unwrap(),0);
    std::fs::remove_file(path).unwrap();
}
