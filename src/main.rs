use flate2::read::MultiGzDecoder;
use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::Path;
use std::time::Instant;

const K: usize = 31;
const INDEX_STEP: usize = 12;
const SEED_TARGET: usize = 720;
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
    fn overhangs(&self, contig:&[u8]) -> Vec<Vec<u8>> {
        if contig.len()<K {return Vec::new();}
        let start=contig.len().saturating_sub(250);
        let mut used=HashSet::<u32>::new();
        let mut ext=Vec::new();
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
                if overlap<K || read_start>=read.len() {continue;}
                let anchor=q-begin;
                let Some(consumed)=overlap_consumed(
                    &read[read_start..], &contig[begin..], anchor) else {continue;};
                used.insert(original);
                ext.push(read[read_start+consumed..].to_vec());
            }
        }
        ext
    }
}
// A single sequencing error outside a 31-mer seed must not discard a
// genuine read spanning the contig end. Exact k-mer anchoring already
// guarantees one long perfect tract; permit at most 2% disagreement in the
// full aligned overlap, with early exit on unrelated/repetitive matches.
fn read_supports_overlap(read: &[u8], contig: &[u8]) -> bool {
    if read.len() != contig.len() || read.len() < K {
        return false;
    }
    let mut errors = 0usize;
    let limit = (read.len() / 50).max(1);
    for (r, c) in read.iter().zip(contig) {
        if r != c {
            errors += 1;
            if errors > limit { return false; }
        }
    }
    true
}

// The anchor is a truly exact 31-mer; only the sequence AFTER that
// read-derived anchor may have a single insertion/deletion. The paired
// FASTQ read then still extends beyond the aligned end of the contig.
// This tolerates a frequent class of sequencer error without relying
// on external references or mapping reads to HXB2.
fn overlap_consumed(read: &[u8], contig: &[u8], anchor: usize) -> Option<usize> {
    let n=contig.len();
    if n<K || anchor+K>n || read.len()<anchor+K {return None;}
    let budget=(n/50).max(1);
    let mut best=None::<(usize,usize)>;
    if read.len()>n && read_supports_overlap(&read[..n],contig) {
        best=Some((read[..n].iter().zip(contig).filter(|(x,y)|x!=y).count(),n));
    }
    let min_k=anchor+K;
    if min_k>=n {return best.map(|(_,consumed)|consumed);}

    let mut left=vec![0usize;n+1];
    let comparable=read.len().min(n);
    for i in 0..comparable {
        left[i+1]=left[i]+usize::from(read[i]!=contig[i]);
    }
    // Insertion in the read relative to contig (one extra read base).
    if read.len()>n+1 {
        let mut suffix=vec![0usize;n+1];
        for i in (0..n).rev() {
            suffix[i]=suffix[i+1]+usize::from(read[i+1]!=contig[i]);
        }
        for k in min_k..n {
            let cost=left[k]+1+suffix[k];
            if cost<=budget && best.is_none_or(|b|cost<b.0) {
                best=Some((cost,n+1));
            }
        }
    }
    // Deletion in the read (one contig base absent from this read).
    if read.len()>=n {
        let mut suffix=vec![0usize;n];
        for k in (0..n-1).rev() {
            suffix[k]=suffix[k+1]+usize::from(read[k]!=contig[k+1]);
        }
        for k in min_k..n {
            let cost=left[k]+1+suffix[k];
            if cost<=budget && best.is_none_or(|b|cost<b.0) {
                best=Some((cost,n-1));
            }
        }
    }
    best.map(|(_,consumed)|consumed)
}

// Experimental de Bruijn fallback. All evidence comes from the input reads;
// no MiCall reference or previous IVA contigs are consulted.
struct SolidKmerGraph {
    next: HashMap<u64, [u32; 4]>,
}

impl SolidKmerGraph {
    fn build(reads: &Reads) -> Self {
        // Only a k-mer independently observed at least ten times in the
        // original seed sample can anchor a graph edge. This rejects most
        // random Illumina errors without storing every erroneous k-mer.
        let mut solid=HashSet::<u64>::new();
        for (&key,&count) in &reads.seed_counts {
            if count < 10 { continue; }
            solid.insert(key);
            solid.insert(encode(&rc(&decode(key))).unwrap());
        }
        let mut next=HashMap::<u64,[u32;4]>::new();
        const MASK: u64 = (1u64 << (2 * K)) - 1;
        for seq in &reads.seqs {
            let mut rolling=0u64;
            let mut valid=0usize;
            for &base in seq {
                let digit=match base {
                    b'A'=>0usize,b'C'=>1,b'G'=>2,b'T'=>3,
                    _=>{rolling=0;valid=0;continue;}
                };
                if valid >= K && solid.contains(&rolling) {
                    let votes=next.entry(rolling).or_insert([0;4]);
                    votes[digit]=votes[digit].saturating_add(1);
                }
                rolling=((rolling << 2)|(digit as u64))&MASK;
                valid=(valid+1).min(K);
            }
        }
        eprintln!("solid read graph: {} oriented k-mers with outgoing evidence",next.len());
        Self { next }
    }

    fn extend_right(&self, seq: &[u8], min_cov:usize, min_ratio:usize) -> Vec<u8> {
        let mut output=seq.to_vec();
        if output.len()<K {return output;}
        let mut visited=HashSet::<u64>::new();
        for prior in output.windows(K).take(output.len()-K) {
            if let Some(key)=encode(prior) { visited.insert(key); }
        }
        while output.len()<MAX_CONTIG_LENGTH {
            let Some(key)=encode(&output[output.len()-K..]) else {break;};
            if !visited.insert(key) {break;}
            let Some(votes)=self.next.get(&key) else {break;};
            let mut ranks=[0usize,1,2,3];
            ranks.sort_unstable_by(|&a,&b|votes[b].cmp(&votes[a]).then(a.cmp(&b)));
            let major=votes[ranks[0]] as usize;
            let minor=votes[ranks[1]] as usize;
            if major<min_cov || major<min_ratio.saturating_mul(minor) {break;}
            output.push([b'A',b'C',b'G',b'T'][ranks[0]]);
        }
        output
    }

    fn extend_both(&self, seq: &[u8], min_cov:usize, min_ratio:usize) -> Vec<u8> {
        let right=self.extend_right(seq,min_cov,min_ratio);
        rc(&self.extend_right(&rc(&right),min_cov,min_ratio))
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
// Biological terminal repeats can legitimately span several hundred bases.
// Require >1kb of identity before declaring a runaway assembly cycle.
const CYCLE_MATCH: usize = 1024;
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
                // The duplicated tract starts at i. Its 512 bases are
                // observation/evidence of a cycle, not new assembled
                // sequence, so retract them from the output contig.
                return Some(i);
            }
        } else {
            first.insert(anchor, i);
        }
    }
    None
}
// Like IVA's retry-after-end-trimming, but only accept a trimmed end if
// independent read evidence recovers MORE bases than the trim discarded.
// This cannot silently shorten an otherwise complete contig.
const STALL_TRIM: usize = 10;

fn recover_stalled_end(
    seq: &[u8], reads: &Reads, min_cov: usize, min_ratio: usize
) -> Option<Vec<u8>> {
    if seq.len() < 2 * K + STALL_TRIM { return None; }
    let mut best: Option<Vec<u8>> = None;
    for reversed in [false, true] {
        let oriented = if reversed { rc(seq) } else { seq.to_vec() };
        let kept = oriented.len() - STALL_TRIM;
        let suffix = choose_extension(&reads.overhangs(&oriented[..kept]), min_cov, min_ratio);
        if suffix.len() <= STALL_TRIM { continue; }
        let mut candidate = oriented[..kept].to_vec();
        candidate.extend_from_slice(&suffix);
        if reversed { candidate = rc(&candidate); }
        if candidate.len() <= seq.len() { continue; }
        if best.as_ref().is_none_or(|other| candidate.len() > other.len()) {
            best = Some(candidate);
        }
    }
    best
}

fn extend(mut seq:Vec<u8>, reads:&Reads, min_cov:usize, min_ratio:usize) -> Vec<u8>{
    let mut stagnant=0usize;
    let mut recovered_stalls=0usize;
    for _ in 0..600 {
        if seq.len()>MAX_CONTIG_LENGTH {break;}
        let right=choose_extension(&reads.overhangs(&seq),min_cov,min_ratio);
        let reversed=rc(&seq);
        let left_rc=choose_extension(&reads.overhangs(&reversed),min_cov,min_ratio);
        let left=rc(&left_rc);
        if right.is_empty() && left.is_empty() {
            if recovered_stalls < 2 {
                if let Some(recovered) = recover_stalled_end(&seq, reads, min_cov, min_ratio) {
                    if let Some(cut) = cycle_end(&recovered) {
                        seq = recovered[..cut].to_vec();
                        break;
                    }
                    recovered_stalls += 1;
                    seq = recovered;
                    continue;
                }
            }
            stagnant += 1;
            if stagnant >= 1 { break; }
        } else {
            stagnant = 0;
        }
        if !left.is_empty() || !right.is_empty() {
            let mut next=Vec::with_capacity(left.len()+seq.len()+right.len());
            next.extend_from_slice(&left);next.extend_from_slice(&seq);next.extend_from_slice(&right);
            if let Some(cut) = cycle_end(&next) {
                eprintln!("extension stopped at repeated >1kb tract ({} nt retained)", cut);
                next.truncate(cut);
                seq = next;
                break;
            }
            seq=next;
        }
    }
    seq
}
fn parse() -> Result<(String,String,String,usize,Option<usize>,Option<String>),String>{
    let args=std::env::args().collect::<Vec<_>>();
    let mut a=None;let mut b=None;let mut output=None;let mut max=12usize;let mut max_pairs=None;let mut seeds=None;
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
                println!("riva --reads1 R1.fastq.gz --reads2 R2.fastq.gz --output contigs.fasta [--max-contigs 12] [--max-pairs N] [--seeds seeds.fasta]");
                std::process::exit(0);
            },
            _=>return Err(format!("unknown/incomplete argument: {}",args[i])),
        }
    }
    Ok((a.ok_or("missing --reads1")?, b.ok_or("missing --reads2")?,output.ok_or("missing --output")?,max,max_pairs,seeds))
}
fn main()->Result<(),Box<dyn std::error::Error>> {
    let (a,b,out,max,max_pairs,seeds_path)=parse().map_err(io::Error::other)?;
    let now=Instant::now();
    let reads=Reads::load(&a,&b,max_pairs)?;
    let graph=SolidKmerGraph::build(&reads);
    let mut candidates=reads.seed_counts.iter().map(|(k,c)|(*k,*c)).collect::<Vec<_>>();
    candidates.sort_unstable_by(|a,b|b.1.cmp(&a.1).then_with(||a.0.cmp(&b.0)));
    let mut contigs=Vec::<Vec<u8>>::new();
    if let Some(ref seeds_file) = seeds_path {
        let supplied=fasta_seeds(seeds_file)?;
        eprintln!("received {} MiCall G2P seed contigs", supplied.len());
        let seed_quota=(max / 3).max(1);
        for seed in supplied.into_iter().filter(|seq|seq.len()>=K).take(seed_quota) {
            let extended=graph.extend_both(&extend(seed,&reads,5,2),5,2);
            if extended.len()>=SEED_TARGET*3/4 &&
               !contigs.iter().any(|c|c.windows(extended.len()).any(|w|w==extended)) {
                contigs.push(extended);
            }
        }
    }
    let mut attempted=0usize;
    for (seed,count) in candidates {
        if contigs.len()>=max || attempted>=500 {break;}
        if count<25 {break;}
        let seedseq=decode(seed);
        let seedrev=rc(&seedseq);
        if contigs.iter().any(|c|c.windows(K).any(|w|w==seedseq || w==seedrev)) {continue;}
        attempted+=1;
        let seq=graph.extend_both(&extend(seedseq,&reads,5,2),5,2);
        if seq.len()>=SEED_TARGET*3/4 {
            eprintln!("candidate {} coverage {} produced {} nt",attempted,count,seq.len());
            // Do not merge contigs, merely suppress exact contained duplicates.
            if !contigs.iter().any(|c|c.windows(seq.len()).any(|w|w==seq)) {
                contigs.push(seq);
            }
        }
        if attempted%20==0 {eprintln!("tried {} seeds, accepted {}",attempted,contigs.len());}
    }
    let mut w=BufWriter::new(File::create(Path::new(&out))?);
    for (i,c) in contigs.iter().enumerate(){
        writeln!(w,">riva_{} len={}",i+1,c.len())?;
        for line in c.chunks(80){w.write_all(line)?;w.write_all(b"\n")?;}
    }
    w.flush()?;
    eprintln!("Riva wrote {} contigs in {:.1}s",contigs.len(),now.elapsed().as_secs_f64());
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn stalled_end_trim_recovers_read_supported_correct_sequence() {
        let mut rng = 0xf1a2b3c4d5e60718u64;
        let target=(0..160).map(|_| {
            rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
            [b'A',b'C',b'G',b'T'][(rng & 3) as usize]
        }).collect::<Vec<_>>();
        let mut damaged = target[..100].to_vec();
        damaged.extend(std::iter::repeat(b'N').take(STALL_TRIM));
        let read=target[50..140].to_vec();
        let key=encode(&target[60..60+K]).unwrap();
        let mut index=HashMap::new();
        index.insert(key, vec![Hit { read:0, pos:10 }]);
        let reads=Reads {
            seqs:vec![read], index, seed_counts:HashMap::new()
        };
        assert_eq!(recover_stalled_end(&damaged,&reads,1,4),
                   Some(target[..140].to_vec()));
        assert_eq!(recover_stalled_end(&target[..100],&Reads{
            seqs:vec![],index:HashMap::new(),seed_counts:HashMap::new()
        },1,4),None);
    }

    #[test]
    fn solid_kmer_graph_joins_high_support_ends_without_a_reference() {
        let mut rng=0x87654321deadbeefu64;
        let sequence=(0..170).map(|_| {
            rng^=rng<<13; rng^=rng>>7; rng^=rng<<17;
            [b'A',b'C',b'G',b'T'][(rng&3) as usize]
        }).collect::<Vec<_>>();
        let mut seed_counts=HashMap::new();
        for w in sequence.windows(K) {
            let key=encode(w).unwrap();
            let rev=encode(&rc(w)).unwrap();
            seed_counts.insert(key.min(rev),25);
        }
        let mut seqs=vec![sequence.clone();12];
        seqs.extend((0..12).map(|_|rc(&sequence)));
        let reads=Reads {seqs,index:HashMap::new(),seed_counts};
        let graph=SolidKmerGraph::build(&reads);
        assert_eq!(graph.extend_both(&sequence[40..100],10,4),sequence);
        assert_eq!(graph.extend_right(b"NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",10,4).len(),K);
    }

    #[test]
    fn solid_graph_does_not_force_a_mixed_population_branch() {
        let key=encode(b"ACGTACGTACGTACGTACGTACGTACGTACG").unwrap();
        let mut next=HashMap::new();
        next.insert(key,[12,7,0,0]);
        let graph=SolidKmerGraph{next};
        let seed=decode(key);
        assert_eq!(graph.extend_right(&seed,10,4),seed);
    }

    #[test] fn reverse_complement(){assert_eq!(rc(b"AAGTNC"),b"GNACTT");}
    #[test] fn encode_roundtrip(){let x=b"ACGTACGTACGTACGTACGTACGTACGTACG"; assert_eq!(decode(encode(x).unwrap()),x);}
    #[test] fn read_external_fasta_seeds() {
        let path=std::env::temp_dir().join(format!("riva-seeds-{}.fasta",std::process::id()));
        std::fs::write(&path,">seed-one\nacgtACGT\n>seed-two\nGGGG\n>ambiguous\nANNN\n").unwrap();
        let seeds=fasta_seeds(path.to_str().unwrap()).unwrap();
        std::fs::remove_file(&path).unwrap();
        assert_eq!(seeds,vec![b"ACGTACGT".to_vec(),b"GGGG".to_vec()]);
    }
    #[test] fn sparse_error_tolerant_overlap_support() {
        let contig=(0..160).map(|i| [b'A',b'C',b'G',b'T'][(i*i/3+i*7)%4])
            .collect::<Vec<_>>();
        let mut read=contig.clone();
        read[7]=match read[7] { b'A'=>b'C', _=>b'A' };
        read.extend_from_slice(b"TTAACCGG");
        let anchor=encode(&contig[60..60+K]).unwrap();
        let mut index=HashMap::new();
        index.insert(anchor,vec![Hit{read:0,pos:60}]);
        let reads=Reads{seqs:vec![read],index,seed_counts:HashMap::new()};
        assert_eq!(reads.overhangs(&contig),vec![b"TTAACCGG".to_vec()]);
        let mut unrelated=contig.clone();
        for i in (0..40).step_by(4) {
            unrelated[i]=match unrelated[i] { b'A'=>b'C', _=>b'A' };
        }
        assert!(!read_supports_overlap(&unrelated,&contig));
    }
    #[test] fn single_indel_after_exact_anchor_extends() {
        let mut rng=0x3a7d5c1f725a12bbu64;
        let contig=(0..160).map(|_|{
            rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;
            [b'A',b'C',b'G',b'T'][(rng&3) as usize]
        }).collect::<Vec<_>>();
        let anchor=60;
        let mut insertion=contig.clone();
        insertion.insert(130,b'A');
        insertion.extend_from_slice(b"GGAATTCC");
        let mut deletion=contig.clone();
        deletion.remove(130);
        deletion.extend_from_slice(b"GGAATTCC");
        assert_eq!(overlap_consumed(&insertion,&contig,anchor),Some(161));
        assert_eq!(overlap_consumed(&deletion,&contig,anchor),Some(159));
        assert_eq!(&insertion[161..],b"GGAATTCC");
        assert_eq!(&deletion[159..],b"GGAATTCC");
        let mut errors=contig.clone();
        for p in (100..150).step_by(4) {errors[p]=b'N';}
        errors.extend_from_slice(b"GGAATTCC");
        assert_eq!(overlap_consumed(&errors,&contig,anchor),None);
    }
    #[test] fn internal_seed_overhang_can_extend() {
        let seed=b"ACGTACGTACGTACGTACGTACGTACGTACG";
        let mut read=vec![b'G';40];
        read.extend_from_slice(seed);
        read.extend_from_slice(b"TTAACCGG");
        let mut index=HashMap::new();
        index.insert(encode(seed).unwrap(),vec![Hit{read:0,pos:40}]);
        let reads=Reads{seqs:vec![read],index,seed_counts:HashMap::new()};
        let ov=reads.overhangs(seed);
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
        assert_eq!(cut, period.len());
    }
    #[test] fn legitimate_terminal_repeat_is_not_a_cycle() {
        // A plausible non-circular sequence with two ~650nt terminal
        // repeats must not be truncated merely due to that duplication.
        let mut rng=0x7265766572736547u64;
        let body=(0..6000).map(|_| {
            rng^=rng<<13; rng^=rng>>7; rng^=rng<<17;
            [b'A',b'C',b'G',b'T'][(rng & 3) as usize]
        }).collect::<Vec<u8>>();
        let repeat=body[..650].to_vec();
        let mut seq=repeat.clone();
        seq.extend_from_slice(&body);
        seq.extend_from_slice(&repeat);
        assert_eq!(cycle_end(&seq),None);
    }
    #[test] fn short_duplicated_tract_is_not_cycle() {
        let mut seq = vec![b'A'; 100];
        seq.extend(std::iter::repeat(b'C').take(4000));
        seq.extend(std::iter::repeat(b'A').take(100));
        assert_eq!(cycle_end(&seq), None);
    }
    #[test] fn low_coverage_extension_requires_real_read_support() {
        let evidence=(0..6).map(|_|b"ACGTTAGC".to_vec()).collect::<Vec<_>>();
        assert!(choose_extension(&evidence,10,2).is_empty());
        assert_eq!(choose_extension(&evidence,5,2),b"ACGTTAGC");
    }
    #[test] fn extension_consensus(){
        let a=(0..16).map(|_|b"ACGTA".to_vec()).collect::<Vec<_>>();
        assert_eq!(choose_extension(&a,10,4),b"ACGTA");
        let mut b=a; b.extend((0..8).map(|_|b"ATGTA".to_vec()));
        assert_eq!(choose_extension(&b,10,4),b"A");
    }
}
