use super::validate;
#[test]
fn absent_preserves_original_limits() {
    assert_eq!(validate(None, 1000), 1000);
    assert_eq!(validate(None, 400), 400);
}
#[test]
fn positive_budget_accepted() {
    assert_eq!(validate(Some("100"), 1000), 100);
    assert_eq!(validate(Some("1"), 400), 1);
}
#[test]
#[should_panic]
fn zero_rejected() {
    validate(Some("0"), 1000);
}
#[test]
#[should_panic]
fn excessive_rejected() {
    validate(Some("2000"), 1000);
}
