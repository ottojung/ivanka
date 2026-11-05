// One byte per possible 51-base observation window, not a machine-word prefix per base.
pub(super) fn valid_windows(quality: &[u8],width:usize)->Vec<u8>{
    if width==0||quality.len()<width{return Vec::new();}
    let mut bad=quality[..width].iter().filter(|&&q|q<48).count();
    let mut out=Vec::with_capacity(quality.len()-width+1);
    out.push(u8::from(bad==0));
    for i in width..quality.len(){
        bad+=usize::from(quality[i]<48);
        bad-=usize::from(quality[i-width]<48);
        out.push(u8::from(bad==0));
    }
    out
}
#[cfg(test)]
mod tests{
    use super::valid_windows;
    #[test] fn exact_window_q15_agrees_with_naive_oracle(){
        let qualities=b"IIII!I0HI!I0!IIIIHH!!!HII";
        for width in 1..=qualities.len()+1 {
            let expected=qualities.windows(width).map(|w|{
                u8::from(w.iter().all(|&q|q>=48))
            }).collect::<Vec<_>>();
            assert_eq!(valid_windows(qualities,width),expected);
        }
    }
    #[test] fn q14_inside_flank_vetoes_full_window(){
        let mut q=vec![b'I';51];
        assert_eq!(valid_windows(&q,51),vec![1]);
        q[25]=47;
        assert_eq!(valid_windows(&q,51),vec![0]);
        q[25]=48;
        assert_eq!(valid_windows(&q,51),vec![1]);
    }
}
