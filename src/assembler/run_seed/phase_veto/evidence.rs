use std::collections::HashMap;
use std::hash::{Hasher,BuildHasherDefault};
pub(super) const A:usize=25; const Q15:u8=48; pub(super) type K128=u128; pub(super) const INV:u64=u64::MAX;
#[derive(Default)] pub(super) struct FastHasher(u64);
impl Hasher for FastHasher{
    fn write(&mut self,b:&[u8]){for &x in b{self.0=self.0.rotate_left(5)^(x as u64);}}
    fn write_u128(&mut self,i:u128){self.0=(i as u64).wrapping_mul(0x9E3779B97F4A7C15)^((i>>64) as u64).wrapping_mul(0xC2B2AE3D27D4EB4F);}
    fn finish(&self)->u64{let mut x=self.0;x^=x>>30;x=x.wrapping_mul(0xBF58476D1CE4E5B9);x^=x>>27;x}
}
pub(super) type FlankIndex=HashMap<K128,Option<usize>,BuildHasherDefault<FastHasher>>;
pub(super) struct Prep{pub km:Vec<u64>,pub lq:Vec<usize>}
fn kcodes(seq:&[u8],a:usize)->Vec<u64>{
    let mut out=vec![INV;seq.len().saturating_sub(a.saturating_sub(1))];
    let (mut f,mut v,mask)=(0u64,0usize,(1u64<<(2*a))-1);
    for (i,&b) in seq.iter().enumerate(){ let d=match b{b'A'=>0,b'C'=>1,b'G'=>2,b'T'=>3,_=>{f=0;v=0;continue}};
        f=((f<<2)&mask)|d; v+=1; if v>=a { out[i+1-a]=f; } } out
}
fn lowq(q:&[u8])->Vec<usize>{ let mut o=vec![0;q.len()+1]; for (i,&x) in q.iter().enumerate(){o[i+1]=o[i]+usize::from(x<Q15);} o }
pub(super) fn validw(p:&[usize],s:usize,e:usize)->bool{ e<p.len() && s<=e && p[s]==p[e] }
fn encode_a(seq:&[u8])->Option<u64>{ let mut n=0u64; for &b in seq { n=(n<<2)|match b{b'A'=>0,b'C'=>1,b'G'=>2,b'T'=>3,_=>return None}; } Some(n) }
pub(super) fn make_preps(reads:&[Vec<u8>],quals:&[Vec<u8>])->Vec<Prep>{
    reads.iter().zip(quals).map(|(r,q)|{ let fallback=vec![b'I';r.len()]; Prep{km:kcodes(r,A),lq:lowq(if q.len()==r.len(){q}else{&fallback})} }).collect() }
// Distinct original R1/R2 sequence signatures are identified once, not per
// candidate. Group indices identify physical read-pair observations; equal
// sequences share an id so they cannot inflate the distinct-signature count.
pub(super) fn signature_ids(reads:&[Vec<u8>])->Vec<u32>{
    let mut map:HashMap<(&[u8],&[u8]),u32>=HashMap::new();
    reads.chunks_exact(4).map(|g|{
        let next=map.len() as u32+1; *map.entry((g[0].as_slice(),g[2].as_slice())).or_insert(next)
    }).collect()
}
pub(super) fn uniq_flanks(seq:&[u8])->FlankIndex{
    let mut out=FlankIndex::default();
    for (i,w) in seq.windows(2*A+1).enumerate(){ if w[A]==b'N'{continue;}
        let (Some(l),Some(r))=(encode_a(&w[..A]),encode_a(&w[A+1..])) else {continue;};
        let key=((l as K128)<<(2*A))|(r as K128);
        out.entry(key).and_modify(|v|if *v!=Some(i+A){*v=None;}).or_insert(Some(i+A)); } out
}
