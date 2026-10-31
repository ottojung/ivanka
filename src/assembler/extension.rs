use std::collections::HashSet;
use super::reads::{K,MAX_EXTENSION,MAX_CONTIG_LENGTH,encode,rc,Reads};
use super::extension_helpers::{summarize,choose_extension as choose_with_limit,CycleTracker};
pub(super) use super::extension_helpers::record_extension_support;

pub(super) fn extend(mut seq:Vec<u8>,reads:&Reads,min_cov:usize,min_ratio:usize)->(Vec<u8>,usize){
    let mut support=HashSet::<u32>::new();
    let (mut r_st,mut l_st,mut cyc)=(false,false,CycleTracker::new());let empty=(Vec::new(),Vec::new());
    for _ in 0..600{
        if seq.len()>MAX_CONTIG_LENGTH{break;}
        let rc_seq=if l_st{None}else{Some(rc(&seq))};
        let right_cached=if r_st{None}else{Some(reads.cached_overhangs(&seq))};
        let (rr,ri)=right_cached.as_deref().unwrap_or(&empty);
        let r=choose_with_limit(rr,min_cov,min_ratio,MAX_EXTENSION);
        let left_cached=if l_st{None}else{Some(reads.cached_overhangs(rc_seq.as_deref().unwrap()))};
        let (lr,li)=left_cached.as_deref().unwrap_or(&empty);
        let lrc_res=choose_with_limit(lr,min_cov,min_ratio,MAX_EXTENSION);
        let l=rc(&lrc_res);
        if seq.len()>=reads.max_read_len{r_st|=r.is_empty();l_st|=l.is_empty();}
        if r.is_empty()&&l.is_empty(){
            if std::env::var_os("IVANKA_TRACE_EXTENSIONS").is_some(){eprintln!("EXTENSION_STOP length={} right_reads={} right_bases={:?} left_reads={} left_bases={:?}",seq.len(),rr.len(),summarize(rr),lr.len(),summarize(lr));}
            break;
        }
        if !l.is_empty()||!r.is_empty(){
            let mut next=Vec::with_capacity(l.len()+seq.len()+r.len());
            next.extend_from_slice(&l);next.extend_from_slice(&seq);next.extend_from_slice(&r);
            if let Some(cut)=cyc.check(&next,K,encode,!l.is_empty()){eprintln!("extension stopped at repeated 512-nt tract ({} nt retained)",cut);next.truncate(cut);seq=next;break;}
            record_extension_support(rr,ri,&r,&mut support);
            record_extension_support(lr,li,&lrc_res,&mut support);
            if next.len()>MAX_CONTIG_LENGTH{reads.overlength_rejections.set(reads.overlength_rejections.get()+1);eprintln!("rejecting assembly path exceeding {} nt",MAX_CONTIG_LENGTH);return (Vec::new(),0);}
            seq=next;
        }
    }
    (seq,support.len())
}
