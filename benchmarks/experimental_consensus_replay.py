"""Replay MiCall aln2counts on saved aligned reads without remapping/Podman.

This is a scientific A/B of a hypothetical mapping arrangement. All original
inputs remain untouched. It must reproduce original baseline before any
candidate score is interpreted; it is NOT a full MiCall qualification.
"""
import argparse
import csv
import json
from contextlib import ExitStack
from pathlib import Path

def replay(scratch, aligned_path, dest):
    from micall.core.aln2counts import aln2counts
    scratch = Path(scratch)
    aligned_path = Path(aligned_path)
    dest = Path(dest)
    if dest.exists():
        raise ValueError("Refusing preexisting replay output directory")
    dest.mkdir(parents=True)
    input_files = {
        "aligned_csv": aligned_path, "clipping_csv": scratch/"clipping.csv",
        "conseq_ins_csv": scratch/"conseq_ins.csv",
        "g2p_aligned_csv": scratch/"g2p_aligned.csv",
        "remap_conseq_csv": scratch/"remap_conseq.csv",
        "contigs_csv": scratch/"contigs.csv",
    }
    output_names = ("nuc_csv", "amino_csv", "insertions_csv", "conseq_csv",
                    "failed_align_csv", "conseq_all_csv", "conseq_region_csv")
    with ExitStack() as stack:
        in_handles = {k:stack.enter_context(path.open()) for k,path in input_files.items()}
        out_handles = {k:stack.enter_context((dest/k.replace("_csv", ".csv")).open("w"))
                       for k in output_names}
        aln2counts(in_handles["aligned_csv"],
                   out_handles["nuc_csv"], out_handles["amino_csv"],
                   out_handles["insertions_csv"], out_handles["conseq_csv"],
                   out_handles["failed_align_csv"],
                   clipping_csv=in_handles["clipping_csv"],
                   conseq_ins_csv=in_handles["conseq_ins_csv"],
                   g2p_aligned_csv=in_handles["g2p_aligned_csv"],
                   remap_conseq_csv=in_handles["remap_conseq_csv"],
                   contigs_csv=in_handles["contigs_csv"],
                   conseq_all_csv=out_handles["conseq_all_csv"],
                   conseq_region_csv=out_handles["conseq_region_csv"])
    return {"aligned_input": str(aligned_path),
            "out": str(dest),
            "max_rows": sum(row.get("consensus-percent-cutoff")=="MAX"
                 for row in csv.DictReader((dest/"conseq.csv").open()))}

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch",type=Path)
    parser.add_argument("aligned_csv",type=Path)
    parser.add_argument("new_output",type=Path)
    args=parser.parse_args()
    print(json.dumps(replay(args.scratch,args.aligned_csv,args.new_output),indent=2))
