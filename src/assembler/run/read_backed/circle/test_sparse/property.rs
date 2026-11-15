use super::locate;

#[test]
fn deterministic_sparse_clusters_require_one_physical_break() {
    for seed in 0..128usize {
        let start = 300 + seed * 29 % 2300;
        let width = 3 + seed * 17 % 220;
        let isolated = start + width + seed % 17;
        let cut = locate(|pos| (start..start + width).contains(&pos) || pos == isolated)
            .expect("one missing interval with one outlier");
        assert!((start..=isolated + 124).contains(&cut));
        if isolated > start + width {
            assert_eq!(
                locate(|pos| (start..start + width).contains(&pos)
                    || (isolated..=isolated + 1).contains(&pos)),
                None,
                "distinct unsupported clusters must reject seed {seed}"
            );
        }
    }
}
