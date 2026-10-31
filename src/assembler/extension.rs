use std::collections::{HashMap, HashSet};
use super::dna::{K, MAX_EXTENSION, MAX_CONTIG_LENGTH, encode, rc};
use super::reads::Reads;

pub(super) fn choose_extension(overhangs:&[Vec<u8>], min_cov:usize, min_ratio:usize)->Vec<u8>{
    let mut out=Vec::new();
    let mut remaining=(0..overhangs.len()).collect::<Vec<_>>();
    for i in 0..MAX_EXTENSION {
        let mut counts=[0usize;4];
        for &x in &remaining {
            if i<overhangs[x].len() {
                match overhangs[x][i] {b'A'=>counts[0]+=1,b'C'=>counts[1]+=1,b'G'=>counts[2]+=1,b'T'=>counts[3]+=1,_=>{}}
            }
        }
        let mut sorted=counts;
        sorted.sort_unstable_by(|a,b|b.cmp(a));
        if sorted[0]<min_cov || sorted[0]<min_ratio.saturating_mul(sorted[1]) {break;}
        let base=match counts.iter().position(|n|*n==sorted[0]).unwrap(){0=>b'A',1=>b'C',2=>b'G',_=>b'T'};
        out.push(base);
        remaining.retain(|x|overhangs[*x].get(i)==Some(&base));
    }
    out
}
// A long exact tract repeated at a distant position signals that extension
// has traversed a cycle/repeat path rather than discovering new sequence.
// Require much more context than a read anchor (31 nt) so short legitimate
// repeats are not mistaken for a circular traversal.
pub(super) const CYCLE_MATCH: usize = 512;
pub(super) const CYCLE_MIN_SPACING: usize = 2000;

pub(super) fn cycle_end(seq: &[u8]) -> Option<usize> {
    if seq.len() < CYCLE_MIN_SPACING + CYCLE_MATCH { return None; }
    let mut first = HashMap::<u64, usize>::new();
    for i in 0..=seq.len() - CYCLE_MATCH {
        let Some(anchor) = encode(&seq[i..i + K]) else { continue; };
        if let Some(&j) = first.get(&anchor) {
            if i - j >= CYCLE_MIN_SPACING
                && seq[j..j + CYCLE_MATCH] == seq[i..i + CYCLE_MATCH]
                && seq[j..j + CYCLE_MATCH]
                    .windows(K).step_by(32)
                    .filter_map(encode).collect::<HashSet<_>>().len() >= 8 {
                return Some(i + CYCLE_MATCH);
            }
        } else {
            first.insert(anchor, i);
        }
    }
    None
}
// A read is credited only if it supports the extension actually taken.
// Read IDs identify individual FASTQ records (including duplicate molecules),
// but the same record is never counted more than once for this contig.
pub(super) fn record_extension_support(suffixes:&[Vec<u8>], ids:&[u32],
                            extension:&[u8], support:&mut HashSet<u32>) {
    if extension.is_empty() { return; }
    for (suffix,&id) in suffixes.iter().zip(ids.iter()) {
        if !suffix.is_empty() &&
           suffix.iter().zip(extension).all(|(a,b)|a==b) &&
           suffix[0]==extension[0] {
            support.insert(id);
        }
    }
}
pub(super) fn extend(mut seq:Vec<u8>, reads:&Reads, min_cov:usize, min_ratio:usize) -> (Vec<u8>,usize){
    let mut stagnant=0usize;
    let mut supporting_reads=HashSet::<u32>::new();
    for _ in 0..600 {
        if seq.len()>MAX_CONTIG_LENGTH {break;}
        let (right_reads,right_ids)=reads.overhangs_with_ids(&seq);
        let right=choose_extension(&right_reads,min_cov,min_ratio);
        let reversed=rc(&seq);
        let (left_reads,left_ids)=reads.overhangs_with_ids(&reversed);
        let left_rc=choose_extension(&left_reads,min_cov,min_ratio);
        let left=rc(&left_rc);
        if right.is_empty() && left.is_empty() {
            if std::env::var_os("IVANKA_TRACE_EXTENSIONS").is_some() {
                let summarize = |overhangs:&[Vec<u8>]| -> [usize;4] {
                    let mut counts=[0usize;4];
                    for o in overhangs {
                        if let Some(&base)=o.first() {
                            match base {b'A'=>counts[0]+=1,b'C'=>counts[1]+=1,
                                b'G'=>counts[2]+=1,b'T'=>counts[3]+=1,_=>{}}
                        }
                    }
                    counts
                };
                eprintln!("EXTENSION_STOP length={} right_reads={} right_bases={:?} left_reads={} left_bases={:?}",
                          seq.len(),right_reads.len(),summarize(&right_reads),
                          left_reads.len(),summarize(&left_reads));
            }
            stagnant+=1; if stagnant>=2 {break;}
        }
        else {stagnant=0;}
        if !left.is_empty() || !right.is_empty() {
            let mut next=Vec::with_capacity(left.len()+seq.len()+right.len());
            next.extend_from_slice(&left);next.extend_from_slice(&seq);next.extend_from_slice(&right);
            if let Some(cut) = cycle_end(&next) {
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
