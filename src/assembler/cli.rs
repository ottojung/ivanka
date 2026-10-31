
pub(super) fn parse() -> Result<(String,String,String,usize,Option<usize>,Option<String>),String>{
    let args=std::env::args().collect::<Vec<_>>();
    let mut a=None;let mut b=None;let mut output=None;let mut max=16usize;let mut max_pairs=None;let mut seeds=None;
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
