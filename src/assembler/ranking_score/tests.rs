use super::select_supported_contigs;
#[test]
fn ranking_favors_evidence_density_over_unverified_span() {
    let long = vec![b'A'; 800];
    let short = vec![b'C'; 400];
    let output = select_supported_contigs(vec![long.clone(), short.clone()], vec![90, 80], 1, 0);
    assert_eq!(output, vec![short]);
}

#[test]
fn cap_prefers_read_supported_quality_over_length() {
    let input = vec![vec![b'A'; 900], vec![b'C'; 180], vec![b'T'; 31]];
    let output = select_supported_contigs(input, vec![1, 9, 0], 2, 0);
    assert_eq!(output.len(), 2);
    assert_eq!(output[0].len(), 180);
    assert_eq!(output[1].len(), 900);
}

#[test]
fn supported_span_leads_among_high_evidence_favorites() {
    // Both top candidates have robust original-read extension support.
    // The long path has greater total evidence but slightly lower density.
    let mut candidates = vec![vec![b'G'; 160]; 31];
    let mut support = vec![20usize; 31];
    candidates.push(vec![b'A'; 10_026]);
    support.push(19_851);
    candidates.push(vec![b'C'; 9_597]);
    support.push(19_156);
    let ranked = super::ranked_candidates(candidates, support, 16, 0);
    assert_eq!(ranked[0].0, 31);
    assert_eq!(ranked[1].0, 32);
}
