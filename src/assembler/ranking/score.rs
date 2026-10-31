use std::collections::HashSet;

pub(super) fn ranked_candidates(seqs: Vec<Vec<u8>>, counts: Vec<usize>, n: usize, protected: usize) -> Vec<(usize, (Vec<u8>, usize))> {
    assert_eq!(seqs.len(),counts.len());
    let mut candidates=seqs.into_iter().zip(counts).enumerate().collect::<Vec<_>>();
    let mut spans=candidates.iter().filter(|(i,(_,reads))|*i>=protected && *reads>0)
        .map(|(i,(seq,reads))|(*i,(*reads as u128)*(seq.len() as u128)))
        .collect::<Vec<_>>();
    spans.sort_unstable_by(|a,b|b.1.cmp(&a.1).then_with(||a.0.cmp(&b.0)));
    let span_favorites=spans.into_iter().take(if candidates.len()>n.saturating_mul(2) {(n/2).min(8)} else {0})
        .map(|(i,_)|i).collect::<HashSet<_>>();
    candidates.sort_unstable_by(|a,b|{
        let a_span=span_favorites.contains(&a.0);
        let b_span=span_favorites.contains(&b.0);
        let a_protected=a.0<protected;
        let b_protected=b.0<protected;
        // Approximate read support per assembled base, to avoid rewarding
        // overextended paths purely for being long. Compare ratios using
        // multiplication rather than truncating integer division.
        let a_score=(a.1.1 as u128)*(b.1.0.len() as u128);
        let b_score=(b.1.1 as u128)*(a.1.0.len() as u128);
        b_protected.cmp(&a_protected)
            .then_with(||b_span.cmp(&a_span))
            .then_with(||b_score.cmp(&a_score))
            .then_with(||b.1.1.cmp(&a.1.1))
            .then_with(||b.1.0.len().cmp(&a.1.0.len()))
            .then_with(||a.1.0.cmp(&b.1.0))
    });
    candidates
}

#[cfg(test)] use super::select_supported_contigs;
    #[test] fn ranking_favors_evidence_density_over_unverified_span() {
        let long=vec![b'A';
        800];
        let short=vec![b'C';
        400];
        let output=select_supported_contigs(
            vec![long.clone(),short.clone()],vec![90,80],1,0);
        assert_eq!(output,vec![short]);
    }

    #[test] fn cap_prefers_read_supported_quality_over_length(){
        let input=vec![vec![b'A';
        900],vec![b'C';
        180],vec![b'T';
        31]];
        let output=select_supported_contigs(input,vec![1,9,0],2,0);
        assert_eq!(output.len(),2);
        assert_eq!(output[0].len(),180);
        assert_eq!(output[1].len(),900);
    }
