use super::{Reads,rc,build_index};

#[test]
fn bounded_left_reverse_complement_matches_full_contig() {
    let mut state=0xdeadbeef12345678u64;
    let mut seq=vec![b'A';25000];
    for b in &mut seq {
        state^=state<<13;state^=state>>7;state^=state<<17;
        *b=b"ACGT"[(state&3) as usize];
    }
    for len in [31,80,179,180,181,250,1000,25000] {
        let contig=&seq[..len];
        let full=rc(contig);
        let mut reads_seq=Vec::new();
        for overlap in [31,42,79,129,160] {
            if overlap>len {continue;}
            let mut read=full[full.len()-overlap..].to_vec();
            read.extend_from_slice(b"ACGTACGTACGT");
            reads_seq.push(read.clone());
            reads_seq.push(rc(&read));
        }
        reads_seq.push(b"N".repeat(180));
        reads_seq.push(b"N".repeat(180));
        let max_read_len=reads_seq.iter().map(Vec::len).max().unwrap();
        let reads=Reads{index:build_index(&reads_seq),seqs:reads_seq,
            max_read_len,seed_counts:Default::default(),
            overhang_cache:Default::default(),overlength_rejections:Default::default(),seen:Default::default()};
        let short=rc(&contig[..contig.len().min(reads.max_read_len)]);
        assert_eq!(reads.overhangs_with_ids(&full),
                   reads.overhangs_with_ids(&short),"len={len}");
        assert_eq!(*reads.cached_overhangs(&full),
                   *reads.cached_overhangs(&short),"cached len={len}");
    }
}
