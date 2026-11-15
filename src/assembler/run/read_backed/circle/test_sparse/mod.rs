use super::breakpoint;

/// The function observes unsupported 125-mer windows, not reference locations.
fn locate(positions: impl Fn(usize) -> bool) -> Option<usize> {
    let core = vec![b'A'; 5500];
    let mut pos = 0usize;
    breakpoint::locate(&core, |_| {
        let missing = positions(pos);
        pos += 1;
        !missing
    })
}

#[test]
fn two_adjacent_or_three_isolated_unsupported_windows_are_not_a_junction() {
    assert_eq!(locate(|p| (2200..2202).contains(&p)), None);
    assert_eq!(locate(|p| [2200, 2205, 2210].contains(&p)), None);
}

#[test]
fn isolated_outlier_may_bridge_sixteen_but_not_seventeen_supported_windows() {
    assert!(locate(|p| (2200..2282).contains(&p) || p == 2298).is_some());
    assert_eq!(locate(|p| (2200..2282).contains(&p) || p == 2299), None);
}

#[test]
fn two_distinct_unsupported_clusters_must_not_be_conflated() {
    assert_eq!(
        locate(|p| (2200..2282).contains(&p) || (2288..2291).contains(&p)),
        None
    );
}

#[test]
fn cluster_may_span_250_but_not_251_window_starts() {
    assert!(locate(|p| (2200..2449).contains(&p) || p == 2449).is_some());
    assert_eq!(locate(|p| (2200..2451).contains(&p)), None);
}

#[test]
fn cut_must_have_a_full_read_window_on_each_side() {
    assert_eq!(locate(|p| (0..8).contains(&p)), None);
    assert_eq!(locate(|p| (5350..5360).contains(&p)), None);
}

#[test]
fn narrow_missing_windows_localize_the_cut_within_their_base_interval() {
    for width in 3..=32 {
        let start = 2100;
        let cut = locate(|p| (start..start + width).contains(&p)).unwrap();
        assert!(cut >= start + width - 1);
        assert!(cut <= start + 124);
    }
}

mod property;
