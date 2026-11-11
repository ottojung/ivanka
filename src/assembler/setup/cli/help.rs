// The usage text distinguishes the default from the absolute safety cap.
pub(super) fn show() {
    println!(concat!(
        "ivanka --reads1 R1.fastq.gz --reads2 R2.fastq.gz ",
        "--output contigs.fasta
",
        "Optional: --max-contigs N (default 16, maximum 1000)
",
        "          --max-pairs N (default unlimited; use to bound memory)
",
        "          --seeds same-sample-reads.fasta
",
        "          --unphased-snv-audit OUTPUT.tsv
",
    ));
}
