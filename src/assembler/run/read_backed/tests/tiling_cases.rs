use super::tiling;
#[test]
fn supported_long_contig_emits_overlapping_cores() {
    let seq = vec![b'G'; 5500];
    let parts = tiling::partition(">sample", &seq, &vec![8; 5470]);
    assert_eq!(parts.len(), 3);
    assert_eq!(parts[0].0, ">sample_tile1");
    assert_eq!(parts[0].1.len(), 2346);
    assert_eq!(parts[1].1.len(), 2345);
    assert_eq!(parts[2].1.len(), 1833);
}
#[test]
fn short_or_unsupported_tiles_remain_whole() {
    let seq = vec![b'A'; 4000];
    assert_eq!(tiling::partition(">x", &seq, &vec![0; 3970]).len(), 1);
    assert_eq!(
        tiling::partition(">x", &seq[..1950], &vec![8; 1920]).len(),
        1
    );
}
