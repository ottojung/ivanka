use super::cycle::{cycle_end, CYCLE_MATCH};
use super::cycle_state::CycleTracker;
use super::test_cycle::encode;

#[test]
fn incremental_cycle_scan_matches_full_rescan() {
    for mode in 0..2 {
        let mut state=0x1234_5678_9abc_def0u64;
        let mut seq=Vec::new();
        let mut tracker=CycleTracker::new();
        let mut found=false;
        for step in 0..100 {
            let mut chunk=vec![b'A';80];
            for b in &mut chunk {
                state^=state<<13;state^=state>>7;state^=state<<17;
                *b=if step%13==0 && state%101==0 {b'N'}
                    else {b"ACGT"[(state&3) as usize]};
            }
            let prepend=mode==1 && step%7==0;
            if prepend {chunk.extend_from_slice(&seq);seq=chunk;}
            else {seq.extend_from_slice(&chunk);}
            if step==72 {
                let repeat=seq[100..100+CYCLE_MATCH+100].to_vec();
                seq.extend_from_slice(&repeat);
            }
            let full=cycle_end(&seq,31,encode);
            let incremental=tracker.check(&seq,31,encode,prepend);
            assert_eq!(incremental,full,"mode={mode} step={step}");
            if full.is_some() {found=true;break;}
        }
        assert!(found,"expected deliberate distant repeat");
    }
}
