use super::breakpoint;

#[test]
fn one_long_unsupported_junction_has_a_bounded_cut() {
    let core = vec![b'A'; 5500];
    let mut scanned = 0;
    let found = breakpoint::locate(&core, |_| {
        let n = scanned;
        scanned += 1;
        !(2200..2403).contains(&n)
    });
    assert_eq!(found, Some(2364));
    let mut scanned = 0;
    assert_eq!(
        breakpoint::locate(&core, |_| {
            let n = scanned;
            scanned += 1;
            !(2200..2500).contains(&n)
        }),
        None
    );
}
