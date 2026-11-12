use super::{island, trimming};
#[test]
fn trim_prefix_preserves_original_depth_alignment() {
    let seq = vec![b'A'; 5800];
    let mut depth = vec![0; seq.len() - 30];
    depth[2800..].fill(10);
    assert_eq!(trimming::bounds(&seq, &depth), (2288, 5800));
    assert_eq!(island::bounds(&seq, &depth), (2288, 5800));
}
#[test]
fn no_support_keeps_the_original() {
    let seq = vec![b'A'; 6000];
    assert_eq!(island::bounds(&seq, &vec![0; 5970]), (0, 6000));
}
#[test]
fn internal_unsupported_gap_selects_the_broadest_island() {
    let seq = vec![b'C'; 6500];
    let mut depth = vec![0; 6470];
    depth[900..2100].fill(10);
    depth[3700..5700].fill(6);
    assert_eq!(island::bounds(&seq, &depth), (3188, 6500));
}
