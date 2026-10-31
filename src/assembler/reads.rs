use std::collections::{HashMap, HashSet};
use std::io;
use super::dna::{K, INDEX_STEP, encode, rc};
use super::input::{read_open, fastq_seq};

#[derive(Clone, Copy, Debug)]
pub(super) struct Hit { pub(super) read: u32, pub(super) pos: u16 }

pub(super) struct Reads {
    pub(super) seqs: Vec<Vec<u8>>,  // forward and reverse complement; index by orientation-specific ID
    pub(super) index: HashMap<u64, Vec<Hit>>,
    pub(super) seed_counts: HashMap<u64, u32>,
}

impl Reads {
    pub(super) fn load(fq1: &str, fq2: &str, max_pairs: Option<usize>) -> io::Result<Self> {
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
    // Returns overhangs from reads overlapping the right end of contig. No aligner or
    // read mapper: a k-mer is only an inverted-index lookup; the full overlap must be exact.
    pub(super) fn overhangs_with_ids(&self, contig:&[u8]) -> (Vec<Vec<u8>>,Vec<u32>) {
        if contig.len()<K {return (Vec::new(),Vec::new());}
        let start=contig.len().saturating_sub(250);
        let mut used=HashSet::<u32>::new();
        let mut ext=Vec::new();
        let mut ids=Vec::new();
        for q in start..=contig.len()-K {
            let Some(key)=encode(&contig[q..q+K]) else {continue;};
            let Some(hits)=self.index.get(&key) else {continue;};
            // Pathological repetitive k-mers cannot be used as reliable extension anchors.
            if hits.len()>50000 {continue;}
            for hit in hits {
                let original=hit.read/2;
                if used.contains(&original) {continue;}
                let pos=hit.pos as usize;
                // The contig may be shorter than the aligned read, especially
                // during seeding. In that case the read starts *before* the
                // contig, and the matching anchor is internal to the read.
                let (begin,read_start)=if q>=pos {(q-pos,0)} else {(0,pos-q)};
                let overlap=contig.len()-begin;
                let read=&self.seqs[hit.read as usize];
                if overlap<K || read_start+overlap>=read.len() {continue;}
                if read[read_start..read_start+overlap]!=contig[begin..] {continue;}
                used.insert(original);
                ext.push(read[read_start+overlap..].to_vec());
                ids.push(original);
            }
        }
        (ext,ids)
    }
}
