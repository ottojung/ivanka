use std::collections::HashMap;
const A:usize=25; const Q15:u8=48; type K128=u128; const INV:u64=u64::MAX;
pub(super) struct Prep{pub km:Vec<u64>,pub lq:Vec<usize>}
fn kcodes(seq:&[u8],a:usize)->Vec<u64>{
    let mut out=vec![INV;seq.len().saturating_sub(a.saturating_sub(1))];
    let (mut f,mut v,mask)=(0u64,0usize,(1u64<<(2*a))-1);
    for (i,&b) in seq.iter().enumerate(){ let d=match b{b'A'=>0,b'C'=>1,b'G'=>2,b'T'=>3,_=>{f=0;v=0;continue}};
        f=((f<<2)&mask)|d; v+=1; if v>=a { out[i+1-a]=f; } } out
}
fn lowq(q:&[u8])->Vec<usize>{ let mut o=vec![0;q.len()+1]; for (i,&x) in q.iter().enumerate(){o[i+1]=o[i]+usize::from(x<Q15);} o }
fn validw(p:&[usize],s:usize,e:usize)->bool{ e<p.len() && s<=e && p[s]==p[e] }
fn encode_a(seq:&[u8])->Option<u64>{ let mut n=0u64; for &b in seq { n=(n<<2)|match b{b'A'=>0,b'C'=>1,b'G'=>2,b'T'=>3,_=>return None}; } Some(n) }
pub(super) fn make_preps(reads:&[Vec<u8>])->Vec<Prep>{ reads.iter().map(|r|Prep{km:kcodes(r,A),lq:lowq(&vec![b'I';r.len()])}).collect() }
fn uniq_flanks(seq:&[u8])->HashMap<K128,Option<usize>>{
    let mut out=HashMap::new();
    for (i,w) in seq.windows(2*A+1).enumerate(){ if w[A]==b'N'{continue;}
        let (Some(l),Some(r))=(encode_a(&w[..A]),encode_a(&w[A+1..])) else {continue;};
        let key=((l as K128)<<(2*A))|(r as K128);
        out.entry(key).and_modify(|v|if *v!=Some(i+A){*v=None;}).or_insert(Some(i+A)); } out
}
struct Pl{st:isize,en:isize,cl:HashMap<usize,u8>}
fn locate(read:&[u8],prep:&Prep,index:&HashMap<K128,Option<usize>>)->Option<Pl>{
    if read.len()<2*A+1||read.len()!=prep.lq.len().saturating_sub(1){return None;}
    let mut st=None; let mut cl=HashMap::new();
    for i in 0..=read.len().saturating_sub(2*A+1){ if !validw(&prep.lq,i,i+2*A+1)||i+A+1>=prep.km.len(){continue;}
        let (l,r)=(prep.km[i],prep.km[i+A+1]); if l==INV||r==INV{continue;}
        let key=((l as K128)<<(2*A))|(r as K128); let Some(Some(pos))=index.get(&key) else {continue;};
        let place=*pos as isize-(i+A) as isize; if place<0||st.is_some_and(|s|s!=place){return None;}
        st=Some(place); let b=read[i+A]; cl.entry(*pos).and_modify(|x|if *x!=b{*x=b'N';}).or_insert(b); }
    cl.retain(|_,b|*b!=b'N'); if cl.len()<2{return None;} let st=st?; Some(Pl{st,en:st+read.len() as isize,cl})
}
fn pair_calls(pr:[&Vec<u8>;4],pp:[&Prep;4],index:&HashMap<K128,Option<usize>>)->HashMap<usize,u8>{
    let o=[locate(pr[0],pp[0],index),locate(pr[1],pp[1],index),locate(pr[2],pp[2],index),locate(pr[3],pp[3],index)];
    let (a,b)=match &o{ [Some(r1),None,None,Some(r2)] if r1.st<=r2.st=>(r1,r2), [None,Some(r1),Some(r2),None] if r2.st<=r1.st=>(r1,r2), _=>return HashMap::new()};
    let longest=pr.iter().map(|r|r.len()).max().unwrap_or(0);
    if (a.en.max(b.en)-a.st.min(b.st)) as usize>longest.saturating_mul(2).saturating_add(200).min(750){return HashMap::new();}
    let mut cl=a.cl.clone(); for (&p,&base) in &b.cl{ cl.entry(p).and_modify(|e|if *e!=base{*e=b'N';}).or_insert(base);} cl.retain(|_,b|*b!=b'N'); cl
}
pub(super) fn observations(seq:&[u8],reads:&[Vec<u8>],preps:&[Prep])->Vec<HashMap<usize,u8>>{
    let index=uniq_flanks(seq);
    reads.chunks_exact(4).zip(preps.chunks_exact(4)).enumerate().map(|(idx,(pr,pp))|{
        let c=pair_calls([&pr[0],&pr[1],&pr[2],&pr[3]],[&pp[0],&pp[1],&pp[2],&pp[3]],&index);
        if idx<2 { let mut k=c.keys().copied().collect::<Vec<_>>(); k.sort(); eprintln!("PC{} n={} {:?}",idx,c.len(),k); }
        c
    }).collect()
}
