use super::{
    approximate_fixtures::{diverged, fixture, path},
    render,
};

#[test]
fn repaired_cycle_path_never_uses_stale_native_spans() {
    let first = path(0x1234_5678_9abc_def0, 4000);
    let (seq, depth, spans) = fixture(diverged(&first), false);
    // Native-coordinate pair evidence still raises the approximate gate.
    assert_eq!(render(None, &seq, &depth, &spans, false).len(), 3);
    // After circle::repair the sequence and depth are rotated while spans
    // remain native: the gate must be skipped and the prior output preserved.
    assert_eq!(
        render(None, &seq, &depth, &spans, true),
        vec![(0, seq.len())]
    );
    // A localized valley remains a join even on a repaired path.
    assert_eq!(
        render(Some((1200, 1270)), &seq, &depth, &spans, true),
        vec![(0, 1231), (1270, seq.len())]
    );
}
