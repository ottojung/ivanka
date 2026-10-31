use super::{K, encode, rc, add_seed_counts};
use std::collections::HashMap;

#[test]
fn rolling_matches_reference() {
    let mut reads=vec![vec![],vec![b'A';K-1],vec![b'T';K],vec![b'N';K+4]];
    for trial in 0..100u64 {
        let mut state=trial+1;
        let mut read=vec![b'A';257];
        for b in &mut read {
            state^=state<<13;state^=state>>7;state^=state<<17;
            *b=if state%127==0 {b'N'} else {b"ACGT"[(state&3) as usize]};
        }
        reads.push(read);
    }
    for read in reads {
        let mut expected=HashMap::new();
        if read.len()>=K {
            for pos in (0..=read.len()-K).step_by(3) {
                if let Some(f)=encode(&read[pos..pos+K]) {
                    let r=encode(&rc(&read[pos..pos+K])).unwrap();
                    *expected.entry(f.min(r)).or_insert(0u32)+=1;
                }
            }
        }
        let mut actual=HashMap::new();
        add_seed_counts(&read,&mut actual);
        assert_eq!(expected,actual);
    }
}
