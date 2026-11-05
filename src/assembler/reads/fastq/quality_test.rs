use super::quality::load_phase_qualities;
use std::fs;
#[test] fn preserves_original_and_reverse_complement_phred_order() {
    let tmp=std::env::temp_dir();
    let a=tmp.join(format!("phase-quality-r1-{}.fq",std::process::id()));
    let b=tmp.join(format!("phase-quality-r2-{}.fq",std::process::id()));
    fs::write(&a,b"@mate/1\nACTG\n+\n!0?I\n").unwrap();
    fs::write(&b,b"@mate/2\nGGTA\n+\nI?0!\n").unwrap();
    let seqs=[b"ACTG".to_vec(),b"CAGT".to_vec(),b"GGTA".to_vec(),b"TACC".to_vec()];
    let result=load_phase_qualities(a.to_str().unwrap(),b.to_str().unwrap(),
                                    None,&seqs).unwrap();
    assert_eq!(result,[b"!0?I".to_vec(),b"I?0!".to_vec(),
                       b"I?0!".to_vec(),b"!0?I".to_vec()]);
    assert!(load_phase_qualities(a.to_str().unwrap(),b.to_str().unwrap(),
          None,&[b"XXXX".to_vec(),seqs[1].clone(),seqs[2].clone(),seqs[3].clone()]).is_err());
    fs::remove_file(a).unwrap();fs::remove_file(b).unwrap();
}
