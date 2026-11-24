//! Adversarial read-pair evidence tests for the de novo phase guard.
//! All truth here is synthetic test data; production takes only reads/quals.
use super::reject_unsupported_recombinants as vet;
fn rc(s:&[u8])->Vec<u8>{s.iter().rev().map(|b|match b{b'A'=>b'T',b'T'=>b'A',b'C'=>b'G',b'G'=>b'C',_=>b'N'}).collect()}
fn scaffold()->Vec<u8>{let mut x=13u64;(0..800).map(|_|{x^=x<<13;x^=x>>7;x^=x<<17;b"ACGT"[(x&3)as usize]}).collect()}
fn at(h:&[u8],ps:&[usize],b:u8)->Vec<u8>{let mut v=h.to_vec();for &p in ps{v[p]=b;}v}
fn pairs(h:&[u8],n:usize,spans:&[(usize,usize)])->Vec<Vec<u8>>{
    let mut r=Vec::new();for (a,b) in spans{for i in 0..n{let x=h[a+i..a+100+i].to_vec();let y=rc(&h[b+i..b+100+i]);
        r.extend([x.clone(),rc(&x),y.clone(),rc(&y)]);}}r}
fn hq(r:&[Vec<u8>])->Vec<Vec<u8>>{r.iter().map(|x|vec![b'I';x.len()]).collect()}

#[test] fn distant_three_snv_double_switch_withheld(){
    let sc=scaffold();let ps=[180,400,560];let a=at(&sc,&ps,b'A');let b=at(&sc,&ps,b'G');
    let reads=pairs(&a,30,&[(140,365),(380,520)]);let reads=[reads,pairs(&b,30,&[(140,365),(380,520)])].concat();
    let q=hq(&reads);let chim=at(&sc,&[ps[0],ps[2]],b'A');let chim=at(&chim,&[ps[1]],b'G');
    let (kept,_)=vet(vec![chim,at(&sc,&ps,b'A'),at(&sc,&ps,b'G')],vec![1,1,1],&reads,&q,0);
    assert_eq!(kept.len(),2,"double switch contradicted by direct pairs must be withheld");
}
#[test] fn genuine_two_haplotype_with_direct_support_kept(){
    let sc=scaffold();let ps=[180,400];let a=at(&sc,&ps,b'A');let b=at(&sc,&ps,b'G');
    let reads=[pairs(&a,30,&[(140,365)]),pairs(&b,30,&[(140,365)])].concat();let q=hq(&reads);
    let (kept,_)=vet(vec![a.clone(),b.clone()],vec![1,1],&reads,&q,0);
    assert_eq!(kept,vec![a,b],"real haplotypes with direct pair support must not be vetoed");
}
#[test] fn zero_bridge_stays_unknown(){
    let sc=scaffold();let a=at(&sc,&[200],b'A');let b=at(&sc,&[700],b'G');
    let reads=[pairs(&a,30,&[(120,230)]),pairs(&b,30,&[(650,660)])].concat();
    // Every pair sits near one SNV; none observes 200 and 700 together.
    let q=hq(&reads);let chim=at(&sc,&[200,700],b'A');
    let (kept,_)=vet(vec![chim.clone()],vec![1],&reads,&q,0);
    assert_eq!(kept,vec![chim],"no pair observes both distant SNVs: phase unknown, keep silent");
}
#[test] fn protected_seed_bypass_is_index_not_sequence(){
    let sc=scaffold();let ps=[200,480];let a=at(&sc,&ps,b'A');let b=at(&sc,&ps,b'G');
    let reads=[pairs(&a,30,&[(160,445)]),pairs(&b,30,&[(160,445)])].concat();let q=hq(&reads);
    let chim=at(&sc,&[ps[0]],b'A');let chim=at(&chim,&[ps[1]],b'G');
    let (kept,_)=vet(vec![chim.clone(),chim],vec![1,1],&reads,&q,1);
    assert_eq!(kept.len(),1,"protected index bypasses veto; identical unprotected copy is withheld");
}
