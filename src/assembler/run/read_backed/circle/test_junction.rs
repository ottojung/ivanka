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

#[test]
fn neighboring_sparse_missing_windows_form_one_bounded_junction() {
    let core = vec![b'A'; 5500];
    let mut scanned = 0;
    let cut = breakpoint::locate(&core, |_| {
        let pos = scanned;
        scanned += 1;
        !((2200..2282).contains(&pos) || pos == 2288)
    });
    assert_eq!(cut, Some(2307));
}

#[test]
fn distant_missing_windows_are_not_a_unique_reopening() {
    let core = vec![b'A'; 5500];
    let mut scanned = 0;
    let cut = breakpoint::locate(&core, |_| {
        let pos = scanned;
        scanned += 1;
        !((2200..2282).contains(&pos) || pos == 2300)
    });
    assert_eq!(cut, None);
}
