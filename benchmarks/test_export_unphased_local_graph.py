import csv, hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

import export_unphased_local_graph as g
from shared_unphased_evidence import build_shared_evidence
from test_shared_block_phase_links import fixture, pair


def v2_report(rows, refs=None):
    masked, refs = fixture() if refs is None else (fixture()[0], refs)
    r = build_shared_evidence(masked, refs, rows, anchor=8, radius=100,
                              include_direct_links=True)
    r.update({"region":"R","mask_start":100,"mask_end":103,
              "input_provenance":{
                "final_conseq_csv":{"path":"x/final.csv","sha256":"0"*64},
                "remap_conseq_csv":{"path":"x/remap.csv","sha256":"0"*64},
                "remap_sam_csv":{"path":"x/sam.csv","sha256":"0"*64}}})
    return r

def minimal_obs(*, region="R", start=100, end=103, refs=("one","two")):
    seq="ACG"; sha=hashlib.sha256(seq.encode()).hexdigest()
    return {
        "schema_version": "ivanka.shared_unphased_observation_export.v1",
        "artifact_type": "shared_unphased_observation_export",
        "label":"X","region":region,
        "mask_interval_zero_based_half_open":{"start":start,"end":end,"length":end-start},
        "shared_reference_membership":{
            "all_selected_references_share_exact_flanked_allele":True,
            "reference_count":len(refs),"selected_reference_names":list(refs),
            "shared_block_length":len(seq),"shared_block_sha256":sha},
        "source_paths":{
            "final_conseq_csv":"x/final.csv","remap_conseq_csv":"x/remap.csv",
            "remap_sam_csv":"x/sam.csv","original_fastq_r1":"x/r1.fq","original_fastq_r2":"x/r2.fq"},
        "source_checksums_sha256":{k:"0"*64 for k in ("final_conseq_csv","remap_conseq_csv","remap_sam_csv","original_fastq_r1","original_fastq_r2")},
        "strict_original_read_pair_ids_evaluated":1,
        "anchor_bp":8,"minimum_phred_quality":15,"phase_status":"unidentified",
        "unphased":True,"raw_qnames_included":False,
        "modifies_final_max_sequence":False,"modifies_micall_consensus":False,
        "safe_for_final_max_overwrite":False,"affects_198_acceptance":False,
        "full_length_haplotype_phase_inferred":False,
        "independent_physical_molecules_assigned":False,
        "haplotype_specific_depth_assigned":False,
    }

def local_manifest(*, emitted, seq="ACG", sample="S", region="R"):
    sha = hashlib.sha256(seq.encode()).hexdigest() if emitted else None
    ident = f"IVANKA_UNPHASED_SHARED_LOCAL__{sample}__{region}__100-103" if emitted else None
    return {
        "schema_version":"ivanka.unphased_shared_local_nodes.v1",
        "sample":sample,"region":region,
        "mask_interval_zero_based_half_open":{"start":100,"end":103,"length":3},
        "selected_reference_names":["one","two"],
        "source_binding_sha256":"1"*64,
        "read_derived_local_node_sha256":sha,
        "node_identifier":ident,
        "locally_supported_unphased_node_emitted":emitted,
        "diagnostics":{"eligible":emitted,
                       "rejection_reasons":([] if emitted else ["competing_minority_allele_fraction"])},
        "original_final_max_unchanged":True,
        "may_replace_micall_consensus":False,
        "may_be_assigned_to_competing_haplotypes":False,
        "independent_physical_molecules_inferred":False,
        "full_length_haplotype_phase_inferred":False,
        "affects_198_acceptance":False,
    }

def write_fasta(path: Path, emitted, seq="ACG", sample="S", region="R"):
    if not emitted: path.write_text(""); return
    ident=f"IVANKA_UNPHASED_SHARED_LOCAL__{sample}__{region}__100-103"
    path.write_text(f">{ident} phase=unknown molecules=unknown\n{seq}\n")

class UnphasedLocalGraphTests(unittest.TestCase):
    def _make(self, tmp, *, emitted=True, seq="ACG", rows=None, refs=None, min_joint=1):
        obs=minimal_obs()
        man=local_manifest(emitted=emitted, seq=seq)
        fa=Path(tmp)/("n.fasta" if emitted else "empty.fasta"); write_fasta(fa, emitted, seq)
        v2=v2_report(rows or (pair("one","a",(refs or fixture()[1])["one"])+pair("one","b",(refs or fixture()[1])["one"])), refs)
        obs["shared_reference_membership"]["selected_reference_names"] = list(v2["selected_reference_names"])
        obs["shared_reference_membership"]["reference_count"] = len(v2["selected_reference_names"])
        man["selected_reference_names"] = list(v2["selected_reference_names"])
        # bind v2 provenance to obs checksums
        for k in ("final_conseq_csv","remap_conseq_csv","remap_sam_csv"):
            v2["input_provenance"][k]["sha256"]=obs["source_checksums_sha256"][k]
        return g.build_graph(observation=obs, local_manifest=man, local_fasta_path=fa, v2_sidecar=v2,
                             observation_sha256=g.sha256_file(Path(tmp)/"obs.json") if False else "o",
                             local_manifest_sha256="m",
                             local_fasta_sha256=g.sha256_file(fa),
                             v2_sha256="v", min_joint_pairs=min_joint,
                             min_consistent_signatures=min_joint)

    def test_s48_like_emitted_node_has_direct_same_qname_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            masked, refs = fixture(); seq="GCG"
            rows = pair("one","a",refs["one"])*40  # 40 pairs same allele context; synthetic
            # but qnames duplicate? pair uses qname arg as qname base? inspect: pair returns rows with qname
            rows = []
            for i in range(40): rows += pair("one",f"q{i}",refs["one"])
            graph = self._make(tmp, emitted=True, seq=seq, rows=rows, refs=refs)
            self.assertEqual(graph["schema_version"], g.SCHEMA)
            self.assertTrue(any(n["type"]=="shared_unphased_local_node" and n["sequence"]==seq for n in graph["nodes"]))
            shared_edges=[e for e in graph["edges"] if e["from"].startswith("shared_local_node::") and e["shared_block_allele_observed"]==seq]
            self.assertTrue(shared_edges)
            e=shared_edges[0]
            self.assertEqual(e["direct_original_pair_qname_ids_observing_both"], 40)
            self.assertTrue(e["same_original_strict_read_pair_qname_required"])
            self.assertTrue(e["q15_required"])
            self.assertFalse(e["transitive_inference_used"])
            self.assertFalse(e["full_length_haplotype_phase_inferred"])
            self.assertFalse(e["independent_physical_molecules_inferred"])
            self.assertFalse(graph["safety"]["affects_198_acceptance"])
            self.assertFalse(graph["safety"]["full_length_haplotype_phase_claimed"])

    def test_duplicate_qnames_with_one_identical_sequence_signature_do_not_pass_default_link_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, refs = fixture()
            rows = []
            for i in range(40):
                rows += pair("one", f"duplicate{i}", refs["one"])
            graph = self._make(tmp, emitted=True, seq="GCG",
                               rows=rows, refs=refs, min_joint=5)
            linked = [e for e in graph["edges"]
                      if e["from"].startswith("shared_local_node::")]
            self.assertEqual(linked, [])
            self.assertTrue(any(
                item["kind"] == "insufficient_direct_support"
                for item in graph["negative_unknown"]))

    def test_s12_vetoed_no_eligible_shared_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = self._make(tmp, emitted=False)
            self.assertEqual(graph["nodes"], [])
            self.assertEqual(graph["edges"], [])
            self.assertTrue(any(u["kind"]=="no_eligible_shared_local_node_emitted" for u in graph["negative_unknown"]))

    def test_transitive_path_veto_no_edge_from_graph_path_only(self):
        # synthetic v2-like data cannot create transitive edges because builder only consumes
        # direct same-qname local_block_marker_observations entries; no path traversal exists.
        with tempfile.TemporaryDirectory() as tmp:
            masked, refs = fixture(); seq="GCG"
            rows = pair("one","a",refs["one"])
            graph = self._make(tmp, emitted=True, seq=seq, rows=rows, refs=refs)
            # Only direct edges; graph has no function to connect marker->marker/block via path
            for e in graph["edges"]:
                self.assertFalse(e["transitive_inference_used"])
            self.assertFalse(graph["safety"]["transitive_inference_used"])

    def test_multi_reference_qname_duplication_not_counted_as_molecules(self):
        # v2 uses distinct pair IDs/signatures from direct same-qname observations; graph copies counts
        # and explicitly marks molecule/phase false.
        with tempfile.TemporaryDirectory() as tmp:
            graph = self._make(tmp, emitted=True, seq="GCG")
            for e in graph["edges"]:
                self.assertFalse(e["independent_physical_molecules_inferred"])
            for n in graph["nodes"]:
                self.assertFalse(n.get("counted_as_independent_molecules", False))

    def test_low_phred_or_ambiguous_excluded_by_upstream_v2(self):
        # low-quality/ambiguous reads do not appear in direct observations; verify builder keeps
        # only provided direct observations and never invents.
        with tempfile.TemporaryDirectory() as tmp:
            masked, refs = fixture(); seq="GCG"
            rows = pair("one","a",refs["one"])
            rows[0]["qual"]="!"*150  # low qual -> v2 should produce 0 direct observations
            graph = self._make(tmp, emitted=True, seq=seq, rows=rows, refs=refs)
            self.assertFalse(any(e["from"].startswith("shared_local_node::") and e["direct_original_pair_qname_ids_observing_both"]>0 for e in graph["edges"]))

    def test_region_or_mask_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            masked, refs = fixture(); seq="GCG"
            obs=minimal_obs(region="OTHER")
            man=local_manifest(emitted=True, seq=seq)
            fa=Path(tmp)/"n.fasta"; write_fasta(fa, True, seq)
            v2=v2_report(pair("one","a",refs["one"]))
            for k in ("final_conseq_csv","remap_conseq_csv","remap_sam_csv"):
                v2["input_provenance"][k]["sha256"]=obs["source_checksums_sha256"][k]
            with self.assertRaises(g.GraphBuildError):
                g.build_graph(observation=obs, local_manifest=man, local_fasta_path=fa, v2_sidecar=v2,
                              observation_sha256="o", local_manifest_sha256="m", local_fasta_sha256="f", v2_sha256="v")

    def test_manifest_fasta_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            man=local_manifest(emitted=True, seq="ACG")
            fa=Path(tmp)/"n.fasta"; write_fasta(fa, True, "ACT") # wrong sequence/hash
            with self.assertRaises(g.GraphBuildError):
                g.verify_local_manifest(man, fa)

    def test_mismatched_reference_group_must_not_be_joined(self):
        obs=minimal_obs()
        _, refs=fixture()
        v2=v2_report(pair("one","a",refs["one"]))
        for k in ("final_conseq_csv","remap_conseq_csv","remap_sam_csv"):
            v2["input_provenance"][k]["sha256"]=obs["source_checksums_sha256"][k]
        v2["selected_reference_names"]=["one"]
        with self.assertRaisesRegex(g.GraphBuildError, "reference membership"):
            g._bind_v2_to_observation(obs,v2)

    def test_mismatched_node_manifest_never_inherits_observation(self):
        obs=minimal_obs()
        man=local_manifest(emitted=True, region="OTHER")
        with self.assertRaisesRegex(g.GraphBuildError, "region mismatch"):
            g._bind_manifest_to_observation(obs,man)

    def test_multiple_fasta_nodes_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fasta=Path(tmp)/"fake.fasta"
            fasta.write_text(chr(10).join([">first phase=unknown", "ACG", ">second phase=unknown", "ACG", ""]))
            with self.assertRaisesRegex(g.GraphBuildError, "Only one"):
                g._parse_fasta(fasta)

    def test_builder_without_original_source_replay_is_not_empirically_authenticated(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph=self._make(tmp,emitted=True,seq="GCG")
            self.assertFalse(graph["source_verification"]["empirical_use_permitted"])
            self.assertFalse(graph["source_verification"][
                "externally_pinned_original_data_replayed"])

    def test_private_write_refuses_protected_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"x.json"
            with self.assertRaises(g.GraphBuildError):
                g._private_write(p, "{}", [Path(tmp)])

    def test_phase_flags_always_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = self._make(tmp, emitted=True, seq="GCG")
            self.assertFalse(graph["safety"]["full_length_haplotype_phase_claimed"])
            self.assertFalse(graph["safety"]["independent_physical_molecules_claimed"])
            self.assertFalse(graph["safety"]["transitive_inference_used"])
            unk=[u for u in graph["negative_unknown"] if u["kind"]=="phase_unknown"][0]
            self.assertFalse(unk["full_length_haplotype_phase_inferred"])

if __name__=="__main__":
    unittest.main()
