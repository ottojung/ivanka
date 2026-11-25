mod evidence;
mod calls;
mod detect;
mod pairscan;
#[cfg(test)] mod test_basic;
#[cfg(test)] mod test_vet_rescue;
#[cfg(test)] mod test_adversarial;
use std::collections::HashMap;
use evidence::Prep;
// Read-derived evidence is computed once per invocation and shared by the
// contig veto and the rescue veto; neither step mutates it.
pub(crate) struct Evidence{preps:Vec<Prep>,sigs:Vec<u32>}
pub(crate) fn prepare(reads:&[Vec<u8>],quals:&[Vec<u8>])->Evidence{
    Evidence{preps:evidence::make_preps(reads,quals),sigs:evidence::signature_ids(reads)}
}
#[cfg(test)] pub(crate) fn reject_unsupported_recombinants(seqs:Vec<Vec<u8>>,counts:Vec<usize>,reads:&[Vec<u8>],quals:&[Vec<u8>],protected:usize)->(Vec<Vec<u8>>,Vec<usize>){
    let ev=prepare(reads,quals); reject_with(&ev,seqs,counts,reads,protected)
}
pub(crate) fn reject_with(ev:&Evidence,seqs:Vec<Vec<u8>>,counts:Vec<usize>,reads:&[Vec<u8>],protected:usize)->(Vec<Vec<u8>>,Vec<usize>){
    let mut kept_s=Vec::new(); let mut kept_c=Vec::new(); let mut dropped=0usize;
    // The verdict is a pure function of (sequence, original read pairs), so
    // repeated candidate sequences are evaluated only once.
    let mut cache=HashMap::<Vec<u8>,bool>::new();
    for (index,(seq,count)) in seqs.into_iter().zip(counts).enumerate(){
        // MiCall-supplied seeds stay protected: their admission belongs to the
        // original-pair-preserving MiCall front, not to this de novo veto.
        let bad=seq.len()>=200&&index>=protected&&*cache.entry(seq.clone()).or_insert_with(||detect::incompatible(&seq,reads,&ev.preps,&ev.sigs));
        if bad{
            dropped+=1; eprintln!("IVANKA_PHASE_GUARD withheld unsupported recombinant candidate ({} nt, support {})",seq.len(),count);
        } else { kept_s.push(seq); kept_c.push(count); }
    }
    if dropped>0 { eprintln!("IVANKA_PHASE_GUARD filtered {} candidate(s) contradicted by direct original-pair evidence",dropped); }
    (kept_s,kept_c)
}
#[cfg(test)] pub(crate) fn vet_rescue(seq:Vec<u8>,reads:&[Vec<u8>],quals:&[Vec<u8>])->Option<Vec<u8>>{
    let ev=prepare(reads,quals); vet_rescue_with(&ev,seq,reads)
}
pub(crate) fn vet_rescue_with(ev:&Evidence,seq:Vec<u8>,reads:&[Vec<u8>])->Option<Vec<u8>>{
    let (mut kept,_)=reject_with(ev,vec![seq],vec![0],reads,0); kept.pop() }
