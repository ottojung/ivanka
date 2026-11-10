use std::io;
use std::time::Instant;
use super::reads::Reads;
use super::ranking::{canonical_kmer,select_supported_contigs,select_supported_contigs_with_kmers};
use super::setup::{parse,balanced_seed_candidates,write_snv_audit,write_fasta};
use super::run_seed::{assemble_candidates,rescue_short,append_preserving_diversity};

pub(crate) fn run()->Result<(),Box<dyn std::error::Error>> {
    let (a,b,out,max,max_pairs,audit_path)=parse().map_err(io::Error::other)?;
    let now=Instant::now();
    let reads=Reads::load(&a,&b,max_pairs)?;
    let candidates=balanced_seed_candidates(&reads.seed_counts);
    let mut contigs=Vec::<Vec<u8>>::new();
    let mut supporting_counts=Vec::<usize>::new();
    let protected_seed_count=0usize;
    assemble_candidates(candidates,&reads,&mut contigs,&mut supporting_counts);
    let rescue=rescue_short(&a,&b,&reads,max_pairs,&contigs)?;
    eprintln!("Ivanka ranking {} candidates by original paired FASTQ contributions × contig length",contigs.len());
    let (mut contigs,audit)=if audit_path.is_some() {
        select_supported_contigs_with_kmers(contigs,supporting_counts,max,protected_seed_count,&reads.seed_counts)
    } else {(select_supported_contigs(contigs,supporting_counts,max,protected_seed_count),Vec::new())};
    if let Some(rescue)=rescue {
        // Never exceed the user-requested max-contigs cap. Replace only a
        // non-protected path whose canonical 31-mers remain represented;
        // otherwise withhold the rescue to avoid losing distinct evidence.
        append_preserving_diversity(&mut contigs,rescue,max,protected_seed_count);
    }
    write_fasta(&out,&contigs)?;
    if let Some(path)=audit_path {
        let count=write_snv_audit(&path,&audit,&contigs,&reads.seed_counts,canonical_kmer)?;
        eprintln!("Ivanka separately observed {} unphased SNV alternatives",count);
    }
    eprintln!("Ivanka wrote {} contigs in {:.1}s",contigs.len(),now.elapsed().as_secs_f64());
    Ok(())
}
