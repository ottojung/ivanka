use super::output;

#[test]
fn split_fragments_have_distinct_blast_and_fasta_ids() {
    let left = output::part_header(0, 1, 4419);
    let right = output::part_header(0, 2, 3623);
    assert_eq!(left, ">ivanka_1_part1 len=4419");
    assert_eq!(right, ">ivanka_1_part2 len=3623");
    assert_ne!(
        left.split_whitespace().next(),
        right.split_whitespace().next()
    );
}
