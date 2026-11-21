mod check;
mod support;

/// Positive physical control: the abundant read-derived path must be emitted,
/// while a sparse distinct path stays minority evidence, without any reference.
#[test]
fn dominant_read_derived_path_is_selected() {
    let dir = support::dir("dominant");
    let dominant = support::template(700, 11);
    let sparse = support::template(306, 23);
    let (r1, r2) = support::read_pairs(&dominant, 3, &sparse, 6);
    support::write_pairs(&dir, &r1, &r2);
    let output = check::run(&dir);
    assert!(
        check::matches_contig(&output, &dominant),
        "dominant path was not emitted"
    );
    assert!(
        !check::matches_contig(&output, &sparse),
        "sparse minority path must not become the dominant result"
    );
}

/// Negative physical control: a tandem repeat may extend into a longer path,
/// but every emitted base must still come from the original read-derived unit.
#[test]
fn tandem_repeat_output_is_entirely_read_derived() {
    let dir = support::dir("repeat");
    let repeat = "ACGT".repeat(150);
    let (r1, r2) = support::read_pairs(&repeat, 3, "", 1);
    support::write_pairs(&dir, &r1, &r2);
    let output = check::run(&dir);
    assert!(
        check::matches_contig(&output, &"ACGT".repeat(2000)),
        "repeat consensus introduced bases absent from its read source"
    );
}
