use super::tiling;
#[test]
fn supported_long_contig_emits_overlapping_cores() {
    let seq = vec![b'G'; 5500];
    let mut depth = vec![8; 5470];
    for start in [400, 2100, 4000] {
        depth[start..start + 110].fill(0);
    }
    let parts = tiling::partition(">sample", &seq, &depth);
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

#[test]
fn continuous_read_supported_genome_is_not_needlessly_fragmented() {
    let sequence = vec![b'A'; 2600];
    let depths = vec![8; 2570];
    let contigs = tiling::partition(">sample", &sequence, &depths);
    assert_eq!(contigs.len(), 1);
    assert_eq!(contigs[0].1, sequence);
}

#[test]
fn dense_but_disconnected_regions_are_still_tiled() {
    let sequence = vec![b'A'; 5500];
    let mut depths = vec![8; 5470];
    depths[2600..2770].fill(0);
    assert_eq!(tiling::partition(">sample", &sequence, &depths).len(), 3);
}

#[test]
fn offset_presentation_matches_direct_slice() {
    let sequence = vec![b'A'; 6000];
    let mut depth = vec![8; 5970];
    depth[3200..3350].fill(0);
    let direct = tiling::partition(">off", &sequence[1200..5200], &depth[1200..5170]);
    let shown = tiling::present(&sequence, &depth, (1200, 5200), ">off");
    assert_eq!(shown, direct);
    assert_eq!(shown.len(), 2);
}
