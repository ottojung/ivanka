use super::limits;

#[test]
fn search_budget_is_a_constant_default() {
    assert_eq!(limits().unwrap(), (50, 20));
    assert_eq!(limits().unwrap(), limits().unwrap());
}
