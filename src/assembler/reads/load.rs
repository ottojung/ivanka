use std::collections::HashMap;
use std::io;
use super::dna::{K, INDEX_STEP, encode, rc};
use super::input::{read_open, fastq_seq};
use super::types::{Hit, Reads};
impl Reads {
    pub(crate) fn load(fq1: &str, fq2: &str, max_pairs: Option<usize>) -> io::Result<Self> {
        let mut r1=read_open(fq1)?; let mut r2=read_open(fq2)?;
        let mut seqs=Vec::new(); let mut seed_counts=HashMap::new();
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
                if pairs < 50000 && read.len() >= K {
                    for pos in (0..=read.len()-K).step_by(3) {
                        if let Some(kmer)=encode(&read[pos..pos+K]) {
                            let rev=rc(&read[pos..pos+K]);
                            let revk=encode(&rev).unwrap();
                            *seed_counts.entry(kmer.min(revk)).or_insert(0) += 1;
                        }
                    }
                }
                seqs.push(read.clone());
                seqs.push(rc(&read));
            }
            pairs += 1;
            if pairs%1000000==0 { eprintln!("loaded {} read pairs",pairs); }
        }
        eprintln!("building index for {} read pairs ({} oriented sequences)",pairs,seqs.len());
        let mut index:HashMap<u64,Vec<Hit>>=HashMap::new();
        for (idx,seq) in seqs.iter().enumerate() {
            if seq.len()<K || seq.len()>u16::MAX as usize {continue;}
            for pos in (0..=seq.len()-K).step_by(INDEX_STEP) {
                if let Some(kmer)=encode(&seq[pos..pos+K]){
                    index.entry(kmer).or_default().push(Hit{read:idx as u32,pos:pos as u16});
                }
            }
            // Always index the last k-mer as well.
            if let Some(kmer)=encode(&seq[seq.len()-K..]){
                index.entry(kmer).or_default().push(Hit{read:idx as u32,pos:(seq.len()-K) as u16});
            }
        }
        eprintln!("index built: {} keys, {} distinct sampled seed kmers",index.len(),seed_counts.len());
        Ok(Self{seqs,index,seed_counts})
    }
}
