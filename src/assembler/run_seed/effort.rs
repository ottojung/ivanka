// Override only exploratory assembly search effort. Without the variable,
// keep the pinned 1000 balanced + 400 deep seed attempts.
fn parse(raw:Option<&str>)->(usize,usize) {
    let count=raw.unwrap_or("1000").parse::<usize>().expect("invalid seed effort");
    assert!((1..=1000).contains(&count),"seed effort must be 1..=1000");
    (count, if count==1000 {400} else {count.min(400)})
}
pub(super) fn seed_limits()->(usize,usize) {
    let value=std::env::var("IVANKA_SEED_EFFORT").ok();
    parse(value.as_deref())
}
#[test] fn default_preserves_original_search() {
    assert_eq!(parse(None),(1000,400));
}
#[test] fn shorter_search_limits_both_stages() {
    assert_eq!(parse(Some("20")),(20,20));
    assert_eq!(parse(Some("80")),(80,80));
    assert_eq!(parse(Some("500")),(500,400));
}
#[test] #[should_panic] fn reject_empty_budget() {
    parse(Some("0"));
}
#[test] #[should_panic] fn reject_non_numeric_budget() {
    parse(Some("abc"));
}
