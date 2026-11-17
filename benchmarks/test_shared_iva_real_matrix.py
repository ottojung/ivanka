"""Real comparator matrix must authenticate single reused IVA control."""
from unittest.mock import patch
import unittest
from expanded import real_matrix
from expanded.adapters import ASSEMBLERS

IMAGES={name:format(i+1,"x")*64 for i,name in enumerate(ASSEMBLERS)}
SAMPLE="s1"

def record(name,reused):
    control={"image_id":IMAGES["iva"],"exit_code":0,
             "timing_origin":"micall_in_container_monotonic_v1",
             "container_wall_seconds":3.,"seconds":2.}
    selected={"image_id":IMAGES[name],"exit_code":0,
              "timing_origin":"micall_in_container_monotonic_v1",
              "container_wall_seconds":4.,"seconds":3.}
    row={"sample":SAMPLE,"status":"finished","failed":False,
         "provenance":{"fastq_sha256":["a"*64,"b"*64]},
         "iva":control,"ivanka":selected,
         "best_contig_acceptance":{
             "iva_score":400.,"ivanka_score":420.,"pass":True,
             "reference_panel_sha256":real_matrix.PANEL,
             "method":"best_final_max_contig_local_alignment_over_reference_panel",
             "reference_count":33}}
    if reused:
        row["iva_baseline_reused"]=True
    return row

class ReuseMatrixTests(unittest.TestCase):
    def test_six_tools_share_one_pinned_iva_control(self):
        specs={name:{"results_jsonl":name,"image_id":IMAGES[name],
                     "control_manifest":"verified-proof" if name!="ivanka" else None}
               for name in ASSEMBLERS if name!="iva"}
        def source_rows(path,*args):
            return {SAMPLE:record(path,path!="ivanka")}
        with patch.object(real_matrix,"source_rows",side_effect=source_rows):
            rows=real_matrix.join_real_runs(specs)
        self.assertEqual(len(rows),1)
        self.assertEqual(set(rows[0]["results"]),set(ASSEMBLERS))
        self.assertEqual(rows[0]["results"]["iva"]["seconds"],2.)
        self.assertEqual(rows[0]["results"]["spades"]["score"],420.)
        del specs["spades"]["control_manifest"]
        with patch.object(real_matrix,"source_rows",side_effect=source_rows):
            with self.assertRaisesRegex(ValueError,"invalid pinned"):
                real_matrix.join_real_runs(specs)

if __name__=="__main__":
    unittest.main()
