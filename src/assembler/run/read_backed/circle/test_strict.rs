use super::breakpoint;

#[test]
fn long_unbridged_linear_junction_has_safe_cut() {
    let core = vec![b'A'; 5000];
    let mut scanned = 0;
    let split = breakpoint::locate_strict(&core, |_| {
        let index = scanned;
        scanned += 1;
        !(2000..2082).contains(&index)
    });
    assert_eq!(split, Some(2103));
}

#[test]
fn sparse_read_dropout_does_not_split_linear_contig() {
    let core = vec![b'A'; 5000];
    let mut scanned = 0;
    let split = breakpoint::locate_strict(&core, |_| {
        let index = scanned;
        scanned += 1;
        !(2000..2005).contains(&index)
    });
    assert_eq!(split, None);
}

#[test]
fn two_separated_junctions_must_not_be_conflated() {
    let core = vec![b'A'; 5000];
    let mut scanned = 0;
    let split = breakpoint::locate_strict(&core, |_| {
        let index = scanned;
        scanned += 1;
        !(2000..2060).contains(&index) && !(2300..2400).contains(&index)
    });
    assert_eq!(split, None);
}

#[test]
fn near_terminal_dropout_cannot_split_long_path() {
    let core = vec![b'A'; 5000];
    let mut scanned = 0;
    let split = breakpoint::locate_strict(&core, |_| {
        let index = scanned;
        scanned += 1;
        !(180..262).contains(&index)
    });
    assert_eq!(split, None);
}
