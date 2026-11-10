use super::vet_rescue;
fn rc(s:&[u8])->Vec<u8>{ s.iter().rev().map(|c|match c{b'A'=>b'T',b'T'=>b'A',b'C'=>b'G',b'G'=>b'C',_=>b'N'}).collect() }
fn setup()->(Vec<u8>,Vec<u8>,Vec<Vec<u8>>,Vec<Vec<u8>>){
    let mut seed=13u64; let mut c=(0..800).map(|_|{seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;b"ACGT"[(seed&3) as usize]}).collect::<Vec<u8>>();
    c[200]=b'A'; c[420]=b'T'; let mut one=c.clone(); one[420]=b'C'; let mut two=c.clone(); two[200]=b'G';
    let mut reads=Vec::new();
    for i in 0..30 { let s=if i%2==0 {&one}else{&two}; let r1=s[140+i..240+i].to_vec(); let r2=rc(&s[365+i..465+i]);
        reads.extend([r1.clone(),rc(&r1),r2.clone(),rc(&r2)]); }
    let quals=reads.iter().map(|r|vec![b'I';r.len()]).collect();
    (c,one,reads,quals)
}
#[test] fn rescue_veto_withholds_chimera_keeps_truth(){
    let (chim,truth,reads,quals)=setup();
    assert!(vet_rescue(chim,&reads,&quals).is_none());
    assert_eq!(vet_rescue(truth.clone(),&reads,&quals),Some(truth));
}
