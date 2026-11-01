use super::{Reads,assemble_candidates,balanced_seed_candidates};
use super::rescue_path::contains_or_rc;
// A high-depth assembly with no long contig may have followed noisy joins.
// Supplement, never replace, the full-read candidates with a bounded prefix.
fn eligible(limit:Option<usize>,oriented:usize,longest:usize,rejects:usize)->bool {
    limit.is_none() && oriented>40000 && longest<1000 && rejects>0
}
#[test] fn only_high_depth_short_assemblies_get_fallback() {
    assert!(eligible(None,40004,715,100));
    assert!(!eligible(None,40000,715,100));
    assert!(!eligible(Some(20000),40004,715,100));
    assert!(!eligible(None,40004,1000,100));
    assert!(!eligible(None,40004,715,0));
}
// Only one independently supported long rescue enters final ranking. The
// full-read minority candidates must not be displaced by a second large pool.
fn best_long(more:Vec<Vec<u8>>,supports:Vec<usize>,original:&[Vec<u8>])->Option<(Vec<u8>,usize)> {
    more.into_iter().zip(supports).filter(|(seq,support)| {
        seq.len()>=1000 && *support>0
            && !original.iter().any(|c|contains_or_rc(c,seq))
    }).max_by_key(|(seq,support)|(*support as u128)*(seq.len() as u128))
}
#[test] fn bounded_rescue_prefers_supported_span() {
    let original=vec![vec![b'T';150]];
    let more=vec![vec![b'A';1200],vec![b'C';2300],vec![b'G';700]];
    let (seq,support)=best_long(more,vec![10,8,100],&original).unwrap();
    assert_eq!((seq.len(),support),(2300,8));
}
#[test] fn rescue_skips_reverse_strand_duplicate_before_scoring() {
    let source=[vec![b'A';500],vec![b'C';700]].concat();
    let reverse=[vec![b'G';700],vec![b'T';500]].concat();
    let novel=vec![b'G';1200];
    let (chosen,support)=best_long(vec![reverse,novel.clone()],vec![100,5],&[source]).unwrap();
    assert_eq!((chosen,support),(novel,5));
}
pub(crate) fn rescue_short(a:&str,b:&str,reads:&Reads,limit:Option<usize>,
    contigs:&[Vec<u8>])->std::io::Result<Option<Vec<u8>>> {
    if !eligible(limit,reads.seqs.len(),contigs.iter().map(Vec::len).max().unwrap_or(0),reads.overlength_rejections.get()){return Ok(None);}
    let subset=Reads::load(a,b,Some(10000))?;
    let (mut more,mut supports)=(Vec::new(),Vec::new());
    assemble_candidates(balanced_seed_candidates(&subset.seed_counts),&subset,&mut more,&mut supports);
    let rescued=best_long(more,supports,contigs).map(|(seq,_)|seq);
    eprintln!("Ivanka high-depth long-contig rescue found {} supported paths",usize::from(rescued.is_some()));
    Ok(rescued)
}
