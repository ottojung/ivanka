use super::tiling;

#[test]
fn offset_presentation_matches_a_direct_slice_and_keeps_tile_overlap() {
    let sequence = vec![b'A'; 6000];
    let mut depth = vec![8; 5970];
    depth[3200..3350].fill(0);
    let (from, to) = (1200, 5200);
    let direct = tiling::partition(">off", &sequence[from..to], &depth[from..to - 30]);
    let presented = tiling::present(&sequence, &depth, (from, to), ">off");
    assert_eq!(presented, direct);
    assert_eq!(presented.len(), 2);
    let overlap = 512;
    assert_eq!(
        &presented[0].1[2000..2000 + overlap],
        &presented[1].1[..overlap]
    );
}

#[test]
fn unsplit_single_interval_is_byte_identical_to_the_original_presentation() {
    let sequence = vec![b'G'; 4200];
    let depth = vec![9; 4170];
    let direct = tiling::partition(">whole", &sequence, &depth);
    let presented = tiling::present(&sequence, &depth, (0, sequence.len()), ">whole");
    assert_eq!(presented, direct);
}
