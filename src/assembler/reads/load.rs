use std::collections::HashMap;
use std::io;
use super::dna::{K, rc};
use super::input::read_open;
use super::fastq::fastq_seq;
use super::types::Reads;
use super::index::build_index;

// Count exactly the same every-third 31-mers, but slide both strand
// encodings across the read rather than rebuilding each 31-base window.
pub(super) fn count_sampled_seed_kmers(read:&[u8], counts:&mut HashMap<u64,u32>) {
    let (mut f,mut r,mut valid)=(0u64,0u64,0usize);
    for (i,&b) in read.iter().enumerate() {
        let d=match b {b'A'=>0,b'C'=>1,b'G'=>2,b'T'=>3,
            _=>{f=0;r=0;valid=0;continue;}};
        f=((f<<2)&((1u64<<62)-1))|d;
        r=(r>>2)|((3-d)<<60);
        valid+=1;
        if valid>=K && (i+1-K)%3==0 {
            *counts.entry(f.min(r)).or_insert(0)+=1;
        }
    }
}
impl Reads {
    pub(crate) fn load(fq1: &str, fq2: &str, max_pairs: Option<usize>) -> io::Result<Self> {
        let mut r1=read_open(fq1)?;
        let mut r2=read_open(fq2)?;
        let mut seqs=Vec::new();
        let mut seed_counts=HashMap::new();
        let mut pairs=0usize;
        loop {
            if max_pairs.is_some_and(|m|pairs>=m) {break;}
            let (a,b)=(fastq_seq(&mut *r1)?,fastq_seq(&mut *r2)?);
            let mismatch=a.is_some()!=b.is_some();
            let (Some(a),Some(b))=(a,b) else {
                if mismatch {return Err(io::Error::new(io::ErrorKind::InvalidData,"unequal mate counts"));}
                break;
            };
            for read in [a,b] {
                if pairs < 50000 {count_sampled_seed_kmers(&read,&mut seed_counts);}
                seqs.push(read.clone());
                seqs.push(rc(&read));
            }
            pairs += 1;
            if pairs%1000000==0 { eprintln!("loaded {} read pairs",pairs); }
        }
        eprintln!("building index for {} read pairs ({} oriented sequences)",pairs,seqs.len());
        let max_read_len=seqs.iter().map(Vec::len).max().unwrap_or(0);
        let index=build_index(&seqs);
        eprintln!("index built: {} keys, {} distinct sampled seed kmers",index.len(),seed_counts.len());
        Ok(Self{seqs,index,seed_counts,max_read_len})
    }
}
