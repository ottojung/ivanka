use super::validate;
#[test]
fn absent_uses_ordinary_search_limits() {
    assert_eq!(validate(None, 50, "primary").unwrap(), 50);
    assert_eq!(validate(None, 20, "rescue").unwrap(), 20);
}
#[test]
fn positive_budget_accepted() {
    assert_eq!(validate(Some("40"), 50, "primary").unwrap(), 40);
    assert_eq!(validate(Some("1"), 20, "rescue").unwrap(), 1);
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
