// Experimental search budgets; defaults reproduce native Ivanka.

use std::env;

fn validate(value:Option<&str>, default:usize)->usize{
    let Some(raw)=value else{return default;};
    let parsed=raw.parse::<usize>().expect("invalid experimental seed limit");
    assert!(parsed>=1 && parsed<=default,"out-of-range experimental seed limit");
    parsed
}

pub(super) fn limits()->(usize,usize){
    let primary=env::var("IVANKA_BENCH_PRIMARY_SEEDS").ok();
    let rescue=env::var("IVANKA_BENCH_RESCUE_SEEDS").ok();
    let limits=(validate(primary.as_deref(),1000),validate(rescue.as_deref(),400));
    eprintln!("IVANKA_SEED_BUDGET primary={} rescue={}",limits.0,limits.1);
    limits
}

#[cfg(test)]
mod tests{
    use super::validate;
    #[test]
    fn absent_preserves_original_limits(){
        assert_eq!(validate(None,1000),1000);
        assert_eq!(validate(None,400),400);
    }
    #[test]
    fn positive_budget_accepted(){
        assert_eq!(validate(Some("100"),1000),100);
        assert_eq!(validate(Some("1"),400),1);
    }
    #[test]
    #[should_panic]
    fn zero_rejected(){validate(Some("0"),1000);}
    #[test]
    #[should_panic]
    fn excessive_rejected(){validate(Some("2000"),1000);}
}
