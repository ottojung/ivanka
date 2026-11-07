mod evidence;
mod detect;
pub(crate) fn reject_unsupported_recombinants(seqs:Vec<Vec<u8>>,counts:Vec<usize>,reads:&[Vec<u8>],quals:&[Vec<u8>])->(Vec<Vec<u8>>,Vec<usize>){
    let preps=evidence::make_preps(reads,quals); let mut kept_s=Vec::new(); let mut kept_c=Vec::new(); let mut dropped=0usize;
    for (seq,count) in seqs.into_iter().zip(counts){
        if seq.len()>=200 && detect::incompatible(&seq,reads,&preps){
            dropped+=1; eprintln!("IVANKA_PHASE_GUARD withheld unsupported recombinant candidate ({} nt, support {})",seq.len(),count);
        } else { kept_s.push(seq); kept_c.push(count); }
    }
    if dropped>0 { eprintln!("IVANKA_PHASE_GUARD filtered {} candidate(s) contradicted by direct original-pair evidence",dropped); }
    (kept_s,kept_c)
}
#[cfg(test)] mod tests{ use super::reject_unsupported_recombinants;
    fn rc(s:&[u8])->Vec<u8>{ s.iter().rev().map(|c|match c{b'A'=>b'T',b'T'=>b'A',b'C'=>b'G',b'G'=>b'C',_=>b'N'}).collect() }
    fn highq(reads:&[Vec<u8>])->Vec<Vec<u8>>{ reads.iter().map(|r|vec![b'I';r.len()]).collect() }
    fn syn(linked:bool)->(Vec<u8>,Vec<u8>,Vec<Vec<u8>>){
        let mut seed=13u64; let mut c=(0..800).map(|_|{seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;b"ACGT"[(seed&3) as usize]}).collect::<Vec<u8>>();
        c[200]=b'A';c[420]=b'T'; let mut one=c.clone();one[420]=b'C'; let mut two=c.clone();two[200]=b'G';
        let mut reads=Vec::new();
        for i in 0..30 { let s=if i%2==0 {&one}else{&two}; let a=140+i; let b=if linked{365+i}else{530+i};
            let r1=s[a..a+100].to_vec(); let r2=rc(&s[b..b+100]); reads.extend([r1.clone(),rc(&r1),r2.clone(),rc(&r2)]); }
        (c,one,reads)
    }
    #[test] fn rejects_linked_recombinant_keeps_truth(){ let (chim,truth,reads)=syn(true);
        let quals=highq(&reads);
        let (s,c)=reject_unsupported_recombinants(vec![chim,truth.clone()],vec![10,9],&reads,&quals); assert_eq!(s,vec![truth]); assert_eq!(c,vec![9]); }
    #[test] fn unlinked_kept_unknown(){ let (chim,_,reads)=syn(false);
        let quals=highq(&reads);
        let (s,_)=reject_unsupported_recombinants(vec![chim.clone()],vec![1],&reads,&quals); assert_eq!(s,vec![chim]); }
    #[test] fn low_quality_prevents_q15_veto_evidence(){
        let (chim,truth,reads)=syn(true);
        let quals=reads.iter().map(|r|vec![b'!';r.len()]).collect::<Vec<_>>();
        let (s,_)=reject_unsupported_recombinants(vec![chim.clone(),truth.clone()],vec![10,9],&reads,&quals);
        assert_eq!(s,vec![chim,truth]);
    }
    #[test] fn q15_boundary_allows_valid_evidence(){
        let (chim,truth,reads)=syn(true);
        let quals=reads.iter().map(|r|vec![b'0';r.len()]).collect::<Vec<_>>(); // Phred+33 Q15
        let (s,_)=reject_unsupported_recombinants(vec![chim,truth.clone()],vec![10,9],&reads,&quals);
        assert_eq!(s,vec![truth]);
    }
}
