use super::fixtures::{fragment, paired_library, rc};
use super::reads;

#[test]
fn reverse_complement_mate_is_merged() {
    let fragment = fragment();
    let read = fragment[..150].to_vec();
    let mate = rc(&fragment[120..]);
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
    assert_eq!(ranked.len(), 2);
    assert_eq!(ranked[0].0, fragment);
    assert_eq!(ranked[1].0, fragment[..150]);
}

#[test]
fn retain_uses_the_reconstructed_fragment() {
    let fragment = fragment();
    let data = paired_library(&fragment, 20);
    let mut contigs = Vec::new();
    assert_eq!(
        super::super::retain(&mut contigs, &data, 16, None).unwrap(),
        1
    );
    assert_eq!(contigs, vec![fragment]);
}
