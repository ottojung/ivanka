use super::{Reads,assemble_candidates,balanced_seed_candidates};
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
pub(crate) fn rescue_short(a:&str,b:&str,reads:&Reads,limit:Option<usize>,
    contigs:&mut Vec<Vec<u8>>,counts:&mut Vec<usize>)->std::io::Result<()> {
    if !eligible(limit,reads.seqs.len(),contigs.iter().map(Vec::len).max().unwrap_or(0),reads.overlength_rejections.get()){return Ok(());}
    let subset=Reads::load(a,b,Some(10000))?;
    let (mut more,mut supports)=(Vec::new(),Vec::new());
    assemble_candidates(balanced_seed_candidates(&subset.seed_counts),&subset,&mut more,&mut supports);
    let mut rescued=0;
    for (seq,support) in more.into_iter().zip(supports) {
        if seq.len()>=1000 && !contigs.iter().any(|c|c.windows(seq.len()).any(|w|w==seq)) {
            contigs.push(seq);counts.push(support);rescued+=1;
        }
    }
    eprintln!("Ivanka high-depth long-contig rescue appended {} supported paths",rescued);
    Ok(())
}
