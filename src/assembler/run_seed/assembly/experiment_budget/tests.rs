use super::validate;
#[test]
fn absent_preserves_original_limits() {
    assert_eq!(validate(None, 1000, "primary").unwrap(), 1000);
    assert_eq!(validate(None, 400, "rescue").unwrap(), 400);
}
#[test]
fn positive_budget_accepted() {
    assert_eq!(validate(Some("100"), 1000, "primary").unwrap(), 100);
    assert_eq!(validate(Some("1"), 400, "rescue").unwrap(), 1);
}
#[test]
fn zero_rejected() {
    assert!(validate(Some("0"), 1000, "primary").is_err());
}
#[test]
fn excessive_rejected() {
    assert!(validate(Some("2000"), 1000, "primary").is_err());
}

#[test]
fn malformed_budget_is_error() {
    assert!(validate(Some("abc"), 400, "rescue").is_err());
}
