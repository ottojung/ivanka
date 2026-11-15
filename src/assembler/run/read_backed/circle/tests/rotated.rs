use super::{alternative::dna, alternative_tail_cut};

#[test]
fn copied_prefix_is_detected_after_a_path_rotation() {
    let first = dna(9400);
    let mut tail = first[..5200].to_vec();
    for i in (400..5200).step_by(10) {
        tail[i] = b"ACGT"[(tail[i] as usize + 1) % 4];
    }
    let mut sequence = first;
    sequence.extend(tail);
    let depths = vec![7; sequence.len() - 30];
    assert_eq!(alternative_tail_cut(&sequence, &depths, 31), Some(9400));
}
