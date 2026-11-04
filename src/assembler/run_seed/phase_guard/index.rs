use std::collections::{HashMap,hash_map::Entry};
pub(super) const INVALID: u64=u64::MAX;
// Encode every exact ACGT a-mer once, sliding in constant time per base.
pub(super) fn kmer_codes(seq: &[u8], a: usize) -> Vec<u64> {
    if a==0 || a>31 {return Vec::new();}
    let mask=(1u64<<(2*a))-1;
    let (mut code,mut valid)=(0u64,0usize);
    let mut out=Vec::with_capacity(seq.len().saturating_sub(a)+1);
    for (i,&b) in seq.iter().enumerate() {
        match b {
            b'A'|b'C'|b'G'|b'T'=>{
                let digit=match b {b'A'=>0,b'C'=>1,b'G'=>2,_=>3};
                code=((code<<2)|digit)&mask;valid+=1;
            },
            _=>{code=0;valid=0;}
        }
        if i+1>=a {out.push(if valid>=a {code} else {INVALID});}
    }
    out
}
pub(super) fn unique_flanks(seq: &[u8], a: usize) -> HashMap<u128,Option<usize>> {
    let mut index=HashMap::new();
    if a==0 || a>31 {return index;}
    let codes=kmer_codes(seq,a);
    for pos in a..seq.len().saturating_sub(a) {
        if !b"ACGT".contains(&seq[pos]) {continue;}
        let (left,right)=(codes[pos-a],codes[pos+1]);
        if left==INVALID || right==INVALID {continue;}
        let key=((left as u128)<<(2*a))|right as u128;
        match index.entry(key) {
            Entry::Vacant(e)=>{e.insert(Some(pos));},
            Entry::Occupied(mut e)=>{e.insert(None);},
        }
    }
    index
}
