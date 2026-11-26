use super::fixtures::{fragment, paired_library, rc};
use super::{reads, sequence};

#[test]
fn exact_mate_overlap_reconstructs_one_observed_fragment() {
    let fragment = fragment();
    let ranked = super::super::support::ranked(&paired_library(&fragment, 20));
    assert_eq!(
        ranked.len(),
        2,
        "merged candidate plus single-read fallback"
    );
    assert_eq!(
        ranked[0].0, fragment,
        "merged bases must be exact observed bases"
    );
    assert_eq!(ranked[1].0, fragment[..150], "fallback stays a real read");
    assert_eq!(ranked[0].1, 20, "distinct-pair support is unchanged");
}

#[test]
fn unrelated_mate_is_not_merged() {
    let read = fragment()[..150].to_vec();
    let mut data = reads();
    for n in 0..20 {
        let mate = sequence(150, 300 + n as u64);
        data.seqs
            .extend([read.clone(), rc(&read), mate.clone(), rc(&mate)]);
    }
    let ranked = super::super::support::ranked(&data);
    assert_eq!(ranked.len(), 1);
    assert_eq!(ranked[0].0, read, "no invented adjacency");
}

#[test]
fn short_overlap_is_not_merged() {
    let read = fragment()[..150].to_vec();
    let mate = fragment()[140..].to_vec();
    let mut data = reads();
    for n in 0..20 {
        let mut mate = mate.clone();
        if n > 0 {
            let at = n % mate.len();
            mate[at] = if mate[at] == b'A' { b'C' } else { b'A' };
        }
        data.seqs
            .extend([read.clone(), rc(&read), mate.clone(), rc(&mate)]);
    }
    let ranked = super::super::support::ranked(&data);
    assert_eq!(ranked.len(), 1);
    assert_eq!(ranked[0].0, read);
}
