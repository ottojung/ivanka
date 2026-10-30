use flate2::read::MultiGzDecoder;
use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::Path;
use std::time::Instant;

const K: usize = 31;
const INDEX_STEP: usize = 12;
const MAX_EXTENSION: usize = 100;
const MAX_CONTIG_LENGTH: usize = 25000;

#[derive(Clone, Copy, Debug)]
struct Hit { read: u32, pos: u16 }

struct Reads {
    seqs: Vec<Vec<u8>>,  // forward and reverse complement; index by orientation-specific ID
    index: HashMap<u64, Vec<Hit>>,
    seed_counts: HashMap<u64, u32>,
}

fn rc(seq: &[u8]) -> Vec<u8> {
    seq.iter().rev().map(|b| match b { b'A' => b'T', b'C' => b'G', b'G' => b'C',
        b'T' => b'A', _ => b'N' }).collect()
}
fn encode(seq: &[u8]) -> Option<u64> {
    if seq.len() != K { return None; }
    let mut n = 0u64;
    for b in seq {
        let d = match b { b'A'=>0, b'C'=>1, b'G'=>2, b'T'=>3, _=>return None };
        n = (n << 2) | d;
    }
    Some(n)
}
fn decode(mut val: u64) -> Vec<u8> {
    let mut out = vec![0; K];
    for x in out.iter_mut().rev() {
        *x = match val & 3 { 0=>b'A',1=>b'C',2=>b'G',_=>b'T' };
        val >>= 2;
    }
    out
}
fn read_open(path: &str) -> io::Result<Box<dyn BufRead>> {
    let f = File::open(path)?;
    if path.ends_with(".gz") {
        Ok(Box::new(BufReader::new(MultiGzDecoder::new(f))))
    } else { Ok(Box::new(BufReader::new(f))) }
}
// G2P-derived MiCall seed contigs. These seed candidates are supplied before
// assembly; this does not require any reference mapping or coordinate lookup.
fn fasta_seeds(path: &str) -> io::Result<Vec<Vec<u8>>> {
    let mut output = Vec::new();
    let mut current = Vec::new();
    let mut started = false;
    for line in read_open(path)?.lines() {
        let line = line?;
        if line.starts_with('>') {
            if started && !current.is_empty() {
                if current.iter().all(|b| matches!(b, b'A'|b'C'|b'G'|b'T')) {
                    output.push(std::mem::take(&mut current));
                } else {current.clear();}
            }
            started = true;
        } else {
            if !started && !line.trim().is_empty() {
                return Err(io::Error::new(io::ErrorKind::InvalidData, "sequence before FASTA header"));
            }
            current.extend(line.trim().bytes().map(|b| b.to_ascii_uppercase()));
        }
    }
    if started && !current.is_empty() && current.iter().all(|b| matches!(b, b'A'|b'C'|b'G'|b'T')) {
        output.push(current);
    }
    Ok(output)
}
fn fastq_seq(r: &mut dyn BufRead) -> io::Result<Option<Vec<u8>>> {
    let mut a=String::new(); let mut b=String::new();
    if r.read_line(&mut a)? == 0 { return Ok(None); }
    if !a.starts_with('@') { return Err(io::Error::new(io::ErrorKind::InvalidData,"invalid FASTQ header")); }
    if r.read_line(&mut b)? == 0 { return Err(io::Error::new(io::ErrorKind::UnexpectedEof,"missing bases")); }
    let mut plus=String::new(); let mut qual=String::new();
    if r.read_line(&mut plus)? == 0 || !plus.starts_with('+') || r.read_line(&mut qual)? == 0 {
        return Err(io::Error::new(io::ErrorKind::InvalidData,"invalid FASTQ record"));
    }
    let seq=b.trim_end().as_bytes().iter().map(|b| b.to_ascii_uppercase()).collect::<Vec<_>>();
    if seq.len()!=qual.trim_end().len() {return Err(io::Error::new(io::ErrorKind::InvalidData,"bases / qualities differ"));}
    Ok(Some(seq))
}
impl Reads {
    fn load(fq1: &str, fq2: &str, max_pairs: Option<usize>) -> io::Result<Self> {
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
    fn overhangs_with_ids(&self, contig:&[u8]) -> (Vec<Vec<u8>>,Vec<u32>) {
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
fn choose_extension(overhangs:&[Vec<u8>], min_cov:usize, min_ratio:usize)->Vec<u8>{
    let mut out=Vec::new();
    let mut remaining=(0..overhangs.len()).collect::<Vec<_>>();
    for i in 0..MAX_EXTENSION {
        let mut counts=[0usize;4];
        for &x in &remaining {
            if i<overhangs[x].len() {
                match overhangs[x][i] {b'A'=>counts[0]+=1,b'C'=>counts[1]+=1,b'G'=>counts[2]+=1,b'T'=>counts[3]+=1,_=>{}}
            }
        }
        let mut sorted=counts;
        sorted.sort_unstable_by(|a,b|b.cmp(a));
        if sorted[0]<min_cov || sorted[0]<min_ratio.saturating_mul(sorted[1]) {break;}
        let base=match counts.iter().position(|n|*n==sorted[0]).unwrap(){0=>b'A',1=>b'C',2=>b'G',_=>b'T'};
        out.push(base);
        remaining.retain(|x|overhangs[*x].get(i)==Some(&base));
    }
    out
}
// A long exact tract repeated at a distant position signals that extension
// has traversed a cycle/repeat path rather than discovering new sequence.
// Require much more context than a read anchor (31 nt) so short legitimate
// repeats are not mistaken for a circular traversal.
const CYCLE_MATCH: usize = 512;
const CYCLE_MIN_SPACING: usize = 2000;

fn cycle_end(seq: &[u8]) -> Option<usize> {
    if seq.len() < CYCLE_MIN_SPACING + CYCLE_MATCH { return None; }
    let mut first = HashMap::<u64, usize>::new();
    for i in 0..=seq.len() - CYCLE_MATCH {
        let Some(anchor) = encode(&seq[i..i + K]) else { continue; };
        if let Some(&j) = first.get(&anchor) {
            if i - j >= CYCLE_MIN_SPACING
                && seq[j..j + CYCLE_MATCH] == seq[i..i + CYCLE_MATCH]
                && seq[j..j + CYCLE_MATCH]
                    .windows(K).step_by(32)
                    .filter_map(encode).collect::<HashSet<_>>().len() >= 8 {
                return Some(i + CYCLE_MATCH);
            }
        } else {
            first.insert(anchor, i);
        }
    }
    None
}
// A read is credited only if it supports the extension actually taken.
// Read IDs identify individual FASTQ records (including duplicate molecules),
// but the same record is never counted more than once for this contig.
fn record_extension_support(suffixes:&[Vec<u8>], ids:&[u32],
                            extension:&[u8], support:&mut HashSet<u32>) {
    if extension.is_empty() { return; }
    for (suffix,&id) in suffixes.iter().zip(ids.iter()) {
        if !suffix.is_empty() &&
           suffix.iter().zip(extension).all(|(a,b)|a==b) &&
           suffix[0]==extension[0] {
            support.insert(id);
        }
    }
}
fn extend(mut seq:Vec<u8>, reads:&Reads, min_cov:usize, min_ratio:usize) -> (Vec<u8>,usize){
    let mut stagnant=0usize;
    let mut supporting_reads=HashSet::<u32>::new();
    for _ in 0..600 {
        if seq.len()>MAX_CONTIG_LENGTH {break;}
        let (right_reads,right_ids)=reads.overhangs_with_ids(&seq);
        let right=choose_extension(&right_reads,min_cov,min_ratio);
        let reversed=rc(&seq);
        let (left_reads,left_ids)=reads.overhangs_with_ids(&reversed);
        let left_rc=choose_extension(&left_reads,min_cov,min_ratio);
        let left=rc(&left_rc);
        if right.is_empty() && left.is_empty() {
            if std::env::var_os("IVANKA_TRACE_EXTENSIONS").is_some() {
                let summarize = |overhangs:&[Vec<u8>]| -> [usize;4] {
                    let mut counts=[0usize;4];
                    for o in overhangs {
                        if let Some(&base)=o.first() {
                            match base {b'A'=>counts[0]+=1,b'C'=>counts[1]+=1,
                                b'G'=>counts[2]+=1,b'T'=>counts[3]+=1,_=>{}}
                        }
                    }
                    counts
                };
                eprintln!("EXTENSION_STOP length={} right_reads={} right_bases={:?} left_reads={} left_bases={:?}",
                          seq.len(),right_reads.len(),summarize(&right_reads),
                          left_reads.len(),summarize(&left_reads));
            }
            stagnant+=1; if stagnant>=2 {break;}
        }
        else {stagnant=0;}
        if !left.is_empty() || !right.is_empty() {
            let mut next=Vec::with_capacity(left.len()+seq.len()+right.len());
            next.extend_from_slice(&left);next.extend_from_slice(&seq);next.extend_from_slice(&right);
            if let Some(cut) = cycle_end(&next) {
                eprintln!("extension stopped at repeated 512-nt tract ({} nt retained)", cut);
                next.truncate(cut);
                seq = next;
                break;
            }
            record_extension_support(&right_reads,&right_ids,&right,&mut supporting_reads);
            record_extension_support(&left_reads,&left_ids,&left_rc,&mut supporting_reads);
            if next.len()>MAX_CONTIG_LENGTH {
                eprintln!("rejecting assembly path exceeding {} nt",MAX_CONTIG_LENGTH);
                return (Vec::new(),0);
            }
            seq=next;
        }
    }
    (seq,supporting_reads.len())
}
// A first-pass ranking heuristic, not a calibrated confidence score:
// independent extension-supporting FASTQ records (with multiplicity) times
// assembled span. Preserve G2P-derived seeds before applying the safety cap.
// Orientation-neutral 31-mer identity, used only to avoid reporting
// redundant assembled paths; it never consumes or filters FASTQ reads.
fn canonical_kmer(seq:&[u8])->Option<u64> {
    let f=encode(seq)?;
    let mut r=0u64;
    for i in 0..K {r=(r<<2)|(3-((f>>(2*i))&3));}
    Some(f.min(r))
}
fn select_supported_contigs(seqs:Vec<Vec<u8>>, counts:Vec<usize>,
                            n:usize, protected:usize)->Vec<Vec<u8>> {
    assert_eq!(seqs.len(),counts.len());
    let mut candidates=seqs.into_iter().zip(counts).enumerate().collect::<Vec<_>>();
    candidates.sort_unstable_by(|a,b|{
        let a_protected=a.0<protected;
        let b_protected=b.0<protected;
        let a_score=(a.1.1 as u128)*(a.1.0.len() as u128);
        let b_score=(b.1.1 as u128)*(b.1.0.len() as u128);
        b_protected.cmp(&a_protected)
            .then_with(||b_score.cmp(&a_score))
            .then_with(||b.1.1.cmp(&a.1.1))
            .then_with(||b.1.0.len().cmp(&a.1.0.len()))
            .then_with(||a.1.0.cmp(&b.1.0))
    });
    // Use read support to prioritize assemblies and k-mer novelty to avoid
    // passing hundreds of near-identical contigs into MiCall's stitcher.
    let mut retained=Vec::new();
    let mut represented=HashSet::new();
    let mut duplicates=0usize;
    let mut no_extension_support=0usize;
    for (index,(seq,support)) in candidates {
        if retained.len()>=n {break;}
        let is_seed=index<protected;
        if !is_seed && support==0 {
            no_extension_support+=1;
            continue;
        }
        let mut valid=0usize;
        let mut shared=0usize;
        for window in seq.windows(K) {
            if let Some(k)=canonical_kmer(window) {
                valid+=1;
                if represented.contains(&k){shared+=1;}
            }
        }
        if !is_seed && valid>0 && shared*20>=valid*19 {
            duplicates+=1;
            continue;
        }
        for window in seq.windows(K) {
            if let Some(k)=canonical_kmer(window) {represented.insert(k);}
        }
        retained.push(seq);
    }
    eprintln!("IVANKA_QUALITY reported={} kmer_redundant={} no_extension_support={}",
              retained.len(),duplicates,no_extension_support);
    retained
}
fn parse() -> Result<(String,String,String,usize,Option<usize>,Option<String>),String>{
    let args=std::env::args().collect::<Vec<_>>();
    let mut a=None;let mut b=None;let mut output=None;let mut max=1000usize;let mut max_pairs=None;let mut seeds=None;
    let mut i=1;
    while i<args.len() {
        match args[i].as_str() {
            "--reads1"|"--reads2"|"--output"|"--max-contigs"|"--max-pairs"|"--seeds" if i+1<args.len()=>{
                match args[i].as_str(){
                    "--reads1"=>a=Some(args[i+1].clone()),
                    "--reads2"=>b=Some(args[i+1].clone()),
                    "--output"=>output=Some(args[i+1].clone()),
                    "--max-contigs"=>max=args[i+1].parse().map_err(|_|"invalid max-contigs")?,
                    "--max-pairs"=>max_pairs=Some(args[i+1].parse().map_err(|_|"invalid max-pairs")?),
                    "--seeds"=>seeds=Some(args[i+1].clone()),
                    _=>{}
                }
                i+=2;
            },
            "--help"|"-h" => {
                println!("ivanka --reads1 R1.fastq.gz --reads2 R2.fastq.gz --output contigs.fasta [--max-contigs 1000] [--max-pairs N] [--seeds seeds.fasta]");
                std::process::exit(0);
            },
            _=>return Err(format!("unknown/incomplete argument: {}",args[i])),
        }
    }
    if max == 0 || max > 1000 { return Err("max-contigs must be in 1..=1000".to_string()); }
    Ok((a.ok_or("missing --reads1")?, b.ok_or("missing --reads2")?,output.ok_or("missing --output")?,max,max_pairs,seeds))
}
// Equal attention to solid k-mers at different sequencing depths prevents
// oversampled regions monopolizing the bounded seed-extension budget.
// This is reference-free and never removes or consumes any reads.
fn balanced_seed_candidates(counts:&HashMap<u64,u32>) -> Vec<(u64,u32)> {
    let mut buckets=vec![Vec::<(u64,u32)>::new();32];
    for (&key,&count) in counts {
        if count < 15 {continue;}
        let level=(31-count.leading_zeros()) as usize;
        buckets[level].push((key,count));
    }
    let mut longest=0usize;
    for bucket in &mut buckets {
        bucket.sort_unstable_by_key(|&(key,_)| key.wrapping_mul(0x9e3779b97f4a7c15));
        longest=longest.max(bucket.len());
    }
    let mut selected=Vec::with_capacity(buckets.iter().map(Vec::len).sum());
    for rank in 0..longest {
        for bucket in buckets.iter().rev() {
            if let Some(&seed)=bucket.get(rank) {selected.push(seed);}
        }
    }
    selected
}
fn main()->Result<(),Box<dyn std::error::Error>> {
    let (a,b,out,max,max_pairs,seeds_path)=parse().map_err(io::Error::other)?;
    let now=Instant::now();
    let reads=Reads::load(&a,&b,max_pairs)?;
    let candidates=balanced_seed_candidates(&reads.seed_counts);
    let mut contigs=Vec::<Vec<u8>>::new();
    let mut supporting_counts=Vec::<usize>::new();
    if let Some(ref seeds_file) = seeds_path {
        let supplied=fasta_seeds(seeds_file)?;
        eprintln!("received {} MiCall G2P seed contigs", supplied.len());
        let seed_quota=(max / 3).max(1);
        for seed in supplied.into_iter().filter(|seq|seq.len()>=K).take(seed_quota) {
            let supplied_len=seed.len(); let (extended,support)=extend(seed,&reads,6,2);
            if extended.len()>=supplied_len &&
               !contigs.iter().any(|c|c.windows(extended.len()).any(|w|w==extended)) {
                contigs.push(extended);
                supporting_counts.push(support);
            }
        }
    }
    let protected_seed_count=contigs.len();
    let mut attempted=0usize;
    for (seed,count) in candidates {
        if attempted>=1000 {break;}
        if count<15 {break;}
        let seedseq=decode(seed);
        let seedrev=rc(&seedseq);
        if contigs.iter().any(|c|c.windows(K).any(|w|w==seedseq || w==seedrev)) {continue;}
        attempted+=1;
        let (seq,support)=extend(seedseq,&reads,4,1);
        if !seq.is_empty() {
            eprintln!("candidate {} coverage {} produced {} nt",attempted,count,seq.len());
            // Do not merge contigs, merely suppress exact contained duplicates.
            if !contigs.iter().any(|c|c.windows(seq.len()).any(|w|w==seq)) {
                contigs.push(seq);
                supporting_counts.push(support);
            }
        }
        if attempted%20==0 {eprintln!("tried {} seeds, accepted {}",attempted,contigs.len());}
    }
    // A second bounded, high-evidence search complements balanced-depth
    // exploration. We deliberately revisit seeds represented in an earlier
    // contig: a different internal anchor can extend through a difficult
    // junction, while final support/novelty selection still de-duplicates.
    let mut deep=reads.seed_counts.iter()
        .filter(|(_,count)|**count>=15)
        .map(|(&seed,&count)|(seed,count)).collect::<Vec<_>>();
    deep.sort_unstable_by(|a,b|b.1.cmp(&a.1).then_with(||a.0.cmp(&b.0)));
    let mut rescued=0usize;
    for (seed,count) in deep.into_iter().take(400) {
        let (seq,support)=extend(decode(seed),&reads,4,1);
        if seq.is_empty() {continue;}
        if !contigs.iter().any(|c|c.windows(seq.len()).any(|w|w==seq)) {
            contigs.push(seq);
            supporting_counts.push(support);
            rescued+=1;
        }
        if rescued%20==0 && rescued>0 {
            eprintln!("high-depth rescue considered seed support {}",count);
        }
    }
    eprintln!("Ivanka supplementary high-depth seeds produced {} novel contigs",rescued);
    eprintln!("Ivanka ranking {} candidates by distinct contributing FASTQ records × contig length; {} MiCall seeds protected",contigs.len(),protected_seed_count);
    let contigs=select_supported_contigs(contigs,supporting_counts,max,protected_seed_count);
    let mut w=BufWriter::new(File::create(Path::new(&out))?);
    for (i,c) in contigs.iter().enumerate(){
        writeln!(w,">ivanka_{} len={}",i+1,c.len())?;
        for line in c.chunks(80){w.write_all(line)?;w.write_all(b"\n")?;}
    }
    w.flush()?;
    eprintln!("Ivanka wrote {} contigs in {:.1}s",contigs.len(),now.elapsed().as_secs_f64());
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn seed_search_spreads_depth_buckets_deterministically() {
        let mut counts=HashMap::new();
        for i in 0..40u64 {
            counts.insert(i+1000,8000);
            counts.insert(i+2000,90);
            counts.insert(i+3000,32);
        }
        counts.insert(7,14);
        let selected=balanced_seed_candidates(&counts);
        assert_eq!(selected.len(),120);
        let early=selected.iter().take(12).map(|(_,c)|*c).collect::<Vec<_>>();
        for expected in [8000,90,32] {
            assert_eq!(early.iter().filter(|c|**c==expected).count(),4);
        }
        assert!(!selected.iter().any(|(k,_)|*k==7));
        assert_eq!(selected,balanced_seed_candidates(&counts));
    }
    #[test] fn cap_prefers_read_supported_quality_over_length(){
        let input=vec![vec![b'A';900],vec![b'C';180],vec![b'T';31]];
        let output=select_supported_contigs(input,vec![1,9,0],2,0);
        assert_eq!(output.len(),2);
        assert_eq!(output[0].len(),180);
        assert_eq!(output[1].len(),900);
    }
    #[test] fn cap_preserves_short_g2p_seed_and_respects_1000(){
        let seqs=(1..=1200).map(|n|vec![b'A';n]).collect::<Vec<_>>();
        let counts=(1..=1200).map(|n|n).collect::<Vec<_>>();
        let out=select_supported_contigs(seqs,counts,1000,1);
        assert!(out.len()<=1000);
        assert!(out.len()>1);
        assert_eq!(out[0].len(),1);
        assert_eq!(out[1].len(),1200);
        assert!(!out.iter().any(|s|s.len()==31));
    }
    #[test] fn support_deduplicates_reused_reads_not_multiplicity(){
        let mut support=HashSet::new();
        let x=vec![b"ACGT".to_vec(),b"ACTG".to_vec(),b"ACGT".to_vec()];
        let ids=vec![3,3,4];
        record_extension_support(&x,&ids,b"AC",&mut support);
        assert_eq!(support,HashSet::from([3,4]));
        record_extension_support(&x,&ids,b"ACG",&mut support);
        assert_eq!(support.len(),2);
        let mut none=HashSet::new();
        record_extension_support(&x,&ids,b"TT",&mut none);
        assert!(none.is_empty());
    }
    #[test] fn reverse_complement(){assert_eq!(rc(b"AAGTNC"),b"GNACTT");}
    #[test] fn encode_roundtrip(){let x=b"ACGTACGTACGTACGTACGTACGTACGTACG"; assert_eq!(decode(encode(x).unwrap()),x);}
    #[test] fn read_external_fasta_seeds() {
        let path=std::env::temp_dir().join(format!("ivanka-seeds-{}.fasta",std::process::id()));
        std::fs::write(&path,">seed-one\nacgtACGT\n>seed-two\nGGGG\n>ambiguous\nANNN\n").unwrap();
        let seeds=fasta_seeds(path.to_str().unwrap()).unwrap();
        std::fs::remove_file(&path).unwrap();
        assert_eq!(seeds,vec![b"ACGTACGT".to_vec(),b"GGGG".to_vec()]);
    }
    #[test] fn internal_seed_overhang_can_extend() {
        let seed=b"ACGTACGTACGTACGTACGTACGTACGTACG";
        let mut read=vec![b'G';40];
        read.extend_from_slice(seed);
        read.extend_from_slice(b"TTAACCGG");
        let mut index=HashMap::new();
        index.insert(encode(seed).unwrap(),vec![Hit{read:0,pos:40}]);
        let reads=Reads{seqs:vec![read],index,seed_counts:HashMap::new()};
        let ov=reads.overhangs_with_ids(seed).0;
        assert_eq!(ov,vec![b"TTAACCGG".to_vec()]);
    }
    #[test] fn distant_cycle_is_stopped() {
        let mut rng=0xdeadbeef12345678u64;
        let period=(0..6000).map(|_|{
            rng^=rng<<13; rng^=rng>>7; rng^=rng<<17;
            [b'A',b'C',b'G',b'T'][(rng & 3) as usize]
        }).collect::<Vec<u8>>();
        let mut seq = period.clone();
        seq.extend_from_slice(&period[..CYCLE_MATCH + 100]);
        let cut = cycle_end(&seq).expect("repeated long tract");
        assert_eq!(cut, period.len() + CYCLE_MATCH);
    }
    #[test] fn short_duplicated_tract_is_not_cycle() {
        let mut seq = vec![b'A'; 100];
        seq.extend(std::iter::repeat(b'C').take(4000));
        seq.extend(std::iter::repeat(b'A').take(100));
        assert_eq!(cycle_end(&seq), None);
    }
    #[test] fn extension_consensus(){
        let a=(0..16).map(|_|b"ACGTA".to_vec()).collect::<Vec<_>>();
        assert_eq!(choose_extension(&a,10,4),b"ACGTA");
        let mut b=a; b.extend((0..8).map(|_|b"ATGTA".to_vec()));
        assert_eq!(choose_extension(&b,10,4),b"A");
    }
}
