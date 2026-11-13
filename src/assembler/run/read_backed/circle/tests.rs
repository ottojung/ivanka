use super::{breakpoint, rotate};

#[test]
fn one_unsupported_junction_selects_read_only_reopening() {
    let seq = vec![b'A'; 3600];
    let mut count = 0;
    let cut = breakpoint::locate(&seq, |_| {
        let position = count;
        count += 1;
        !(1570..1574).contains(&position)
    });
    assert_eq!(cut, Some(1632));
}

#[test]
fn no_evidence_or_multiple_breaks_preserves_the_path() {
    let seq = vec![b'A'; 3600];
    assert_eq!(breakpoint::locate(&seq, |_| true), None);
    let mut count = 0;
    assert_eq!(
        breakpoint::locate(&seq, |_| {
            let position = count;
            count += 1;
            position != 1500 && position != 2400
        }),
        None
    );
}

#[test]
fn rotation_preserves_exact_original_31_mer_depth() {
    let core = (0..3400)
        .map(|i| b"ACGT"[(i * 7 / 11) % 4])
        .collect::<Vec<_>>();
    let mut cycle = core.clone();
    cycle.extend_from_slice(&core[..512]);
    let depth = (0..cycle.len() - 30).map(|i| i as u32).collect::<Vec<_>>();
    let (linear, scores) = rotate::at(&cycle, &depth, 1612, 512, 31).unwrap();
    assert_eq!(linear, [&core[1612..], &core[..1612]].concat());
    assert_eq!(scores.len(), linear.len() - 30);
    assert_eq!(linear[0..31], cycle[1612..1643]);
    assert_eq!(scores[0], depth[1612]);
    let last = 1612 + scores.len() - 1;
    let last = if last <= cycle.len() - 31 {
        last
    } else {
        last - core.len()
    };
    assert_eq!(scores.last(), depth.get(last));
}
