use std::collections::HashSet;
use super::reads::{K, MAX_EXTENSION, MAX_CONTIG_LENGTH, encode, rc, Reads};
use super::extension_helpers::{summarize, choose_extension as choose_with_limit, cycle_end as detect_cycle};
pub(super) use super::extension_helpers::record_extension_support;

pub(super) fn extend(mut seq:Vec<u8>, reads:&Reads, min_cov:usize, min_ratio:usize) -> (Vec<u8>,usize){
    let mut supporting_reads=HashSet::<u32>::new();
    let (mut right_stalled,mut left_stalled)=(false,false);
    for _ in 0..600 {
        if seq.len()>MAX_CONTIG_LENGTH {break;}
        let (right_reads,right_ids)=if right_stalled {(Vec::new(),Vec::new())}
            else {reads.overhangs_with_ids(&seq)};
        let right=choose_with_limit(&right_reads,min_cov,min_ratio,MAX_EXTENSION);
        let (left_reads,left_ids)=if left_stalled {(Vec::new(),Vec::new())}
            else {reads.overhangs_with_ids(&rc(&seq))};
        let left_rc=choose_with_limit(&left_reads,min_cov,min_ratio,MAX_EXTENSION);
        let left=rc(&left_rc);
        // Once a contig covers every possible read, extending the opposite
        // end cannot change the last read-length bases at a stalled end.
        if seq.len()>=reads.max_read_len {
            right_stalled |= right.is_empty();
            left_stalled |= left.is_empty();
        }
        if right.is_empty() && left.is_empty() {
            if std::env::var_os("IVANKA_TRACE_EXTENSIONS").is_some() {
                eprintln!("EXTENSION_STOP length={} right_reads={} right_bases={:?} left_reads={} left_bases={:?}",
                          seq.len(),right_reads.len(),summarize(&right_reads),
                          left_reads.len(),summarize(&left_reads));
            }
            // With no extension, the same immutable reads and contig produce
            // the same result next iteration. A second probe is redundant.
            break;
        }
        if !left.is_empty() || !right.is_empty() {
            let mut next=Vec::with_capacity(left.len()+seq.len()+right.len());
            next.extend_from_slice(&left);
            next.extend_from_slice(&seq);
            next.extend_from_slice(&right);
            if let Some(cut) = detect_cycle(&next,K,encode) {
                eprintln!("extension stopped at repeated 512-nt tract ({} nt retained)", cut);
                next.truncate(cut);
                seq = next;
                break;
            }
            record_extension_support(&right_reads,&right_ids,&right,&mut supporting_reads);
            record_extension_support(&left_reads,&left_ids,&left_rc,&mut supporting_reads);
            if next.len()>MAX_CONTIG_LENGTH {
                eprintln!("rejecting assembly path exceeding {} nt",MAX_CONTIG_LENGTH);
                return (Vec::new(),0);
            }
            seq=next;
        }
    }
    (seq,supporting_reads.len())
}
