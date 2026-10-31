use std::collections::HashMap;
use std::io;
use super::dna::rc;
use super::index::add_seed_counts;
use super::input::read_open;
use super::fastq::fastq_seq;
use super::types::Reads;
use super::index::build_index;
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
                if pairs < 50000 { add_seed_counts(&read, &mut seed_counts); }
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
