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
