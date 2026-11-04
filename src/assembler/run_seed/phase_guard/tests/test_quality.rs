use super::test_support::{qualities,synthetic};
use super::{collect::observations,detect::incompatible_link,split::split_unsupported_contigs};
#[test] fn q14_flank_or_variant_cannot_support_phase_link() {
    let (candidate,_,reads)=synthetic(true);
    let high=qualities(&reads);
    assert!(incompatible_link(&candidate,&reads,
        &observations(&candidate,&reads,&high,25)).is_some());
    let low=reads.iter().map(|r|vec![47u8;r.len()]).collect::<Vec<_>>();
    assert!(observations(&candidate,&reads,&low,25).iter().all(|c|c.is_empty()));
    assert_eq!(split_unsupported_contigs(vec![candidate.clone()],&reads,&low,2),
               vec![candidate]);
}
#[test] fn malformed_or_missing_quality_arrays_fail_closed() {
    let (candidate,_,reads)=synthetic(true);
    let mut quality=qualities(&reads);
    quality[0].pop();
    let calls=observations(&candidate,&reads,&quality,25);
    assert!(calls[0].is_empty());
    quality.pop();
    assert!(observations(&candidate,&reads,&quality,25).is_empty());
}
