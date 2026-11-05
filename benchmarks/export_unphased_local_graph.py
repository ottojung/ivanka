"""Build an optional typed SHARED/UNPHASED local graph from authenticated inputs.

Consumes: #169 shared unphased observation export, #170 local-node FASTA/manifest
(only when strictly eligible), and #164 original-pair direct-marker v2 sidecar.
Outputs JSON graph for research; never mutates MiCall consensus/FASTQs/MAX,
never changes 198/IVA/reference/gate logic, and never claims independent
molecules or full-length phase.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os
from pathlib import Path

SCHEMA = "ivanka.unphased_local_graph.v1"
OBS_SCHEMA = "ivanka.shared_unphased_observation_export.v1"
NODE_SCHEMA = "ivanka.unphased_shared_local_nodes.v1"
V2_SCHEMA = "ivanka.shared_unphased_evidence_direct.v2"

class GraphBuildError(ValueError):
    pass

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""): h.update(b)
    return h.hexdigest()

def _load_json(path: Path):
    return json.loads(Path(path).read_text())

def _require(cond, msg):
    if not cond: raise GraphBuildError(msg)

def _parse_fasta(path: Path):
    text = Path(path).read_text()
    if not text.strip(): return None, None
    lines = [l.rstrip("\n\r") for l in text.splitlines() if l.strip()]
    _require(lines and lines[0].startswith(">"), "FASTA must start with header")
    seq = "".join(l.strip() for l in lines[1:] if not l.startswith(">")).upper()
    _require(seq and set(seq) <= set("ACGT"), "FASTA sequence must be resolved A/C/G/T")
    _require(sum(line.startswith(">") for line in lines) == 1,
             "Only one explicitly unphased local FASTA node is allowed")
    return lines[0][1:].strip(), seq

def verify_observation(obs, expected_sha=None):
    _require(isinstance(obs, dict) and obs.get("schema_version") == OBS_SCHEMA,
             f"observation must be {OBS_SCHEMA}")
    for k in ("unphased","modifies_final_max_sequence","safe_for_final_max_overwrite",
              "full_length_haplotype_phase_inferred","independent_physical_molecules_assigned"):
        v = obs.get(k)
        _require(v is False or (k=="unphased" and v is True),
                 f"observation safety flag {k} invalid")
    _require(obs.get("phase_status") == "unidentified", "observation phase must be unidentified")
    _require(obs.get("raw_qnames_included") is False, "observation must not include raw qnames")
    _require(isinstance(obs.get("source_paths"), dict), "observation source_paths required")
    _require(isinstance(obs.get("source_checksums_sha256"), dict), "observation checksums required")
    return obs

def verify_local_manifest(manifest, fasta_path: Path, expected_manifest_sha=None, expected_fasta_sha=None):
    _require(isinstance(manifest, dict) and manifest.get("schema_version") == NODE_SCHEMA,
             f"local manifest must be {NODE_SCHEMA}")
    required_false = ("may_replace_micall_consensus","may_be_assigned_to_competing_haplotypes",
                      "independent_physical_molecules_inferred","full_length_haplotype_phase_inferred",
                      "affects_198_acceptance")
    for k in required_false:
        _require(manifest.get(k) is False, f"local manifest safety flag {k} invalid")
    _require(manifest.get("original_final_max_unchanged") is True,
             "local manifest must preserve original final MAX")
    emitted = manifest.get("locally_supported_unphased_node_emitted")
    _require(isinstance(emitted, bool), "manifest emitted flag required")
    header, seq = _parse_fasta(fasta_path)
    if expected_fasta_sha is not None:
        _require(sha256_file(fasta_path) == expected_fasta_sha, "FASTA SHA256 mismatch")
    if not emitted:
        _require(seq is None, "vetoed local node must have empty FASTA")
        _require(manifest.get("read_derived_local_node_sha256") is None, "vetoed node has no allele hash")
        return manifest, None, None
    _require(header and seq, "eligible local node requires FASTA header+sequence")
    allele_sha = hashlib.sha256(seq.encode()).hexdigest()
    _require(manifest.get("read_derived_local_node_sha256") == allele_sha,
             "manifest allele SHA256 disagrees with FASTA")
    ident = manifest.get("node_identifier")
    _require(isinstance(ident,str) and header.split()[0] == ident, "FASTA identifier mismatch")
    return manifest, ident, seq

def verify_v2(v2, expected_sha=None):
    _require(isinstance(v2, dict) and v2.get("schema_version") == V2_SCHEMA, f"direct sidecar must be {V2_SCHEMA}")
    _require(v2.get("phase_status") == "unidentified", "v2 phase must be unidentified")
    _require(v2.get("raw_qnames_included") is False, "v2 must not include raw qnames")
    _require(v2.get("full_length_haplotype_phase_inferred") is False, "v2 cannot infer phase")
    _require(isinstance(v2.get("marker_direct_links"), list), "v2 marker_direct_links required")
    prov = v2.get("input_provenance")
    _require(isinstance(prov, dict), "v2 input_provenance required for source authentication binding")
    for name, entry in prov.items():
        _require(isinstance(entry, dict) and isinstance(entry.get("path"), str)
                 and isinstance(entry.get("sha256"), str) and len(entry["sha256"]) == 64,
                 f"v2 provenance {name} invalid")
    return v2

def _bind_v2_to_observation(obs, v2):
    # Require same region/mask and source identity where overlapping.
    _require(obs.get("region") == v2.get("region"), "observation/v2 region mismatch")
    mask = obs.get("mask_interval_zero_based_half_open") or {}
    _require(mask.get("start") == v2.get("mask_start") and mask.get("end") == v2.get("mask_end"),
             "observation/v2 mask mismatch")
    obs_src = obs.get("source_paths") or {}
    obs_sha = obs.get("source_checksums_sha256") or {}
    prov = v2["input_provenance"]
    _require(v2.get("selected_reference_names") ==
             obs.get("shared_reference_membership",{}).get("selected_reference_names"),
             "v2/observation reference membership mismatch")
    mapping = (("final_conseq_csv","final_conseq_csv"),
               ("remap_conseq_csv","remap_conseq_csv"),
               ("remap_sam_csv","remap_sam_csv"))
    for obs_key, prov_key in mapping:
        _require(prov_key in prov and obs_key in obs_sha
                 and obs_key in obs_src, f"Missing source binding: {obs_key}")
        _require(prov[prov_key]["sha256"] == obs_sha[obs_key],
                 f"v2/observation source SHA mismatch: {obs_key}")


def _bind_manifest_to_observation(obs, manifest):
    _require(manifest.get("region") == obs.get("region"),
             "Manifest/observation region mismatch")
    _require(manifest.get("mask_interval_zero_based_half_open") ==
             obs.get("mask_interval_zero_based_half_open"),
             "Manifest/observation mask mismatch")
    _require(manifest.get("selected_reference_names") ==
             obs.get("shared_reference_membership",{}).get("selected_reference_names"),
             "Manifest/observation selected references mismatch")


def replay_original_sources(args, observation, manifest):
    """Never classify local graph edges as authentic without reobserving sources.

    The caller independently pins the MiCall source root, sample identity,
    cohort screen hash, original R1/R2, and exact artifact hashes.
    """
    from export_unphased_local_nodes import compute
    from verify_shared_unphased_sidecar import verify
    expected_fasta, expected_manifest = compute(
        observation, artifact_dir=args.artifact_dir,
        screen_ledger=args.screen_ledger,
        screen_sha256=args.screen_sha256,
        sample=args.sample,
        fastq_r1=args.original_fastq_r1,
        fastq_r2=args.original_fastq_r2,
        depth=args.depth,
        min_fraction=args.minimum_fraction,
        min_complete_signatures=args.min_complete_signatures)
    _require(manifest == expected_manifest,
             "Local-node manifest disagrees with authenticated recomputation")
    _require(args.local_node_fasta.read_text() == expected_fasta,
             "Local FASTA disagrees with authenticated read-derived sequence")
    status = verify(
        args.direct_v2_sidecar, args.artifact_dir,
        args.original_fastq_r1, args.original_fastq_r2)
    _require(status.get("original_fastq_provenance") ==
             "sequence_and_phred_authenticated_per_original_mate",
             "Direct-link read-pair source was not authenticated to original FASTQs")
    return status


def build_graph(*, observation, local_manifest, local_fasta_path, v2_sidecar,
                observation_sha256, local_manifest_sha256, local_fasta_sha256,
                v2_sha256, min_joint_pairs=5, min_consistent_signatures=5,
                sample=None):
    _require(type(min_joint_pairs) is int and min_joint_pairs >= 1, "min_joint_pairs >= 1")
    _require(type(min_consistent_signatures) is int and min_consistent_signatures >= 1,
             "min_consistent_signatures >= 1")
    obs = verify_observation(observation)
    _bind_v2_to_observation(obs, v2_sidecar)
    v2 = verify_v2(v2_sidecar)
    manifest, node_id, node_seq = verify_local_manifest(local_manifest, local_fasta_path,
                                                        expected_fasta_sha=None)
    _bind_manifest_to_observation(obs, manifest)
    sample_name = sample or manifest.get("sample") or obs.get("label")
    region = obs["region"]
    mask = obs["mask_interval_zero_based_half_open"]

    nodes = []
    edges = []
    negative_unknown = []
    emitted_node_id = None
    if node_seq is not None:
        emitted_node_id = f"shared_local_node::{node_id}"
        nodes.append({
            "id": emitted_node_id,
            "type": "shared_unphased_local_node",
            "status": "emitted_strictly_eligible_local_only",
            "sequence": node_seq,
            "sequence_sha256": hashlib.sha256(node_seq.encode()).hexdigest(),
            "source_node_identifier": node_id,
            "counted_as_independent_molecules": False,
            "full_length_haplotype_phase_proven": False,
            "assigned_to_competing_haplotypes": False,
            "safe_for_final_max_overwrite": False,
        })
    else:
        negative_unknown.append({
            "kind": "no_eligible_shared_local_node_emitted",
            "reason": "vetoed_or_not_eligible_per_170_manifest",
            "rejection_reasons": (manifest.get("diagnostics") or {}).get("rejection_reasons", []),
            "affects_emitted_node": True,
        })

    # Marker nodes and direct same-qname local-block->marker edges from v2.
    # v2 contains local_block_marker_observations derived from same original strict
    # read-pair qname observing complete local block and marker at Q15 (redacted IDs).
    # We never invent qnames and never create transitive edges.
    other_block_nodes = {}
    for marker in v2["marker_direct_links"]:
        if emitted_node_id is None:
            negative_unknown.append({
                "kind": "vetoed_local_node_no_graph_promotion",
                "marker_index": marker.get("marker_index"),
                "observed_direct_pairs_not_promoted_to_graph":
                    marker.get("direct_joint_observation_count", 0),
                "reason": "no_strictly_eligible_unphased_shared_node",
            })
            continue
        midx = marker.get("marker_index")
        pos = marker.get("reference_positions_zero_based") or {}
        for obs_item in marker.get("local_block_marker_observations") or []:
            block_allele = obs_item.get("shared_block_allele")
            marker_allele = obs_item.get("marker_allele")
            joint_pairs = obs_item.get("original_pair_ids_directly_observing_both")
            joint_sigs = obs_item.get("consistent_distinct_pair_sequence_signatures")
            _require(isinstance(block_allele,str) and set(block_allele)<=set("ACGT"), "bad v2 block allele")
            _require(isinstance(marker_allele,str) and marker_allele in "ACGT", "bad v2 marker allele")
            _require(type(joint_pairs) is int and joint_pairs >= 0, "bad v2 joint pair count")
            _require(type(joint_sigs) is int and joint_sigs >= 0, "bad v2 joint signature count")
            mnode_id = f"marker_allele::{region}::idx{midx}::{marker_allele}"
            if not any(n["id"] == mnode_id for n in nodes):
                nodes.append({
                    "id": mnode_id,
                    "type": "observed_marker_allele_context",
                    "marker_index": midx,
                    "allele": marker_allele,
                    "reference_positions_zero_based": pos,
                    "counted_as_independent_molecules": False,
                    "full_length_haplotype_phase_proven": False,
                })
            qualifies = (joint_pairs >= min_joint_pairs and joint_sigs >= min_consistent_signatures)
            # Connect only the emitted shared local node allele to marker if same block allele.
            if emitted_node_id and block_allele == node_seq and qualifies:
                edges.append({
                    "id": f"edge::direct_same_qname_local_only::{emitted_node_id}::{mnode_id}::{block_allele}->{marker_allele}",
                    "type": "tentative_local_direct_observation",
                    "from": emitted_node_id,
                    "to": mnode_id,
                    "shared_block_allele_observed": block_allele,
                    "marker_allele_observed": marker_allele,
                    "direct_original_pair_qname_ids_observing_both": joint_pairs,
                    "consistent_distinct_pair_sequence_signatures": joint_sigs,
                    "same_original_strict_read_pair_qname_required": True,
                    "q15_required": True,
                    "raw_qnames_disclosed": False,
                    "full_length_haplotype_phase_inferred": False,
                    "independent_physical_molecules_inferred": False,
                    "transitive_inference_used": False,
                    "assigns_to_competing_haplotype": False,
                    "modifies_final_max_sequence": False,
                    "status": "local_only_tentative_supported_by_direct_same_qname",
                })
            elif emitted_node_id and block_allele == node_seq and not qualifies:
                negative_unknown.append({
                    "kind": "insufficient_direct_support",
                    "from": emitted_node_id, "to": mnode_id,
                    "shared_block_allele_observed": block_allele,
                    "marker_allele_observed": marker_allele,
                    "direct_original_pair_qname_ids_observing_both": joint_pairs,
                    "consistent_distinct_pair_sequence_signatures": joint_sigs,
                    "threshold": {"min_joint_pairs": min_joint_pairs,
                                  "min_consistent_signatures": min_consistent_signatures},
                })
            elif block_allele != (node_seq or ""):
                # Different observed complete block allele: preserve as distinct observed node, not emitted shared node.
                bnode_id = f"observed_local_block_allele::{region}::{hashlib.sha256(block_allele.encode()).hexdigest()[:16]}"
                if bnode_id not in other_block_nodes:
                    other_block_nodes[bnode_id] = block_allele
                    nodes.append({
                        "id": bnode_id,
                        "type": "observed_unphased_local_block_allele_not_emitted_as_shared_node",
                        "sequence": block_allele,
                        "sequence_sha256": hashlib.sha256(block_allele.encode()).hexdigest(),
                        "emitted_as_eligible_shared_local_node": False,
                        "counted_as_independent_molecules": False,
                        "full_length_haplotype_phase_proven": False,
                    })
                if qualifies:
                    edges.append({
                        "id": f"edge::direct_same_qname_local_only::{bnode_id}::{mnode_id}::{block_allele}->{marker_allele}",
                        "type": "tentative_local_direct_observation",
                        "from": bnode_id, "to": mnode_id,
                        "shared_block_allele_observed": block_allele,
                        "marker_allele_observed": marker_allele,
                        "direct_original_pair_qname_ids_observing_both": joint_pairs,
                        "consistent_distinct_pair_sequence_signatures": joint_sigs,
                        "same_original_strict_read_pair_qname_required": True,
                        "q15_required": True,
                        "raw_qnames_disclosed": False,
                        "full_length_haplotype_phase_inferred": False,
                        "independent_physical_molecules_inferred": False,
                        "transitive_inference_used": False,
                        "assigns_to_competing_haplotype": False,
                        "modifies_final_max_sequence": False,
                        "status": "local_only_tentative_supported_by_direct_same_qname",
                        "note": "observed_block_allele_distinct_from_emitted_shared_local_node",
                    })

        if marker.get("direct_joint_observation_count", 0) == 0:
            negative_unknown.append({
                "kind": "no_direct_same_qname_block_marker_observation",
                "marker_index": midx,
                "reference_positions_zero_based": pos,
            })
        elif emitted_node_id and not any(e["to"] == f"marker_allele::{region}::idx{midx}::" + o.get("marker_allele","") and e["from"] == emitted_node_id for e in edges for o in marker.get("local_block_marker_observations") or [] if o.get("shared_block_allele")==node_seq):
            # marker has observations but maybe none involving emitted allele after thresholding
            emitted_obs = [o for o in marker.get("local_block_marker_observations") or [] if o.get("shared_block_allele")==node_seq]
            if not emitted_obs:
                negative_unknown.append({
                    "kind": "no_direct_observation_linking_emitted_shared_node_allele_to_marker",
                    "marker_index": midx, "emitted_shared_node_id": emitted_node_id,
                })

    # Explicit global unknowns
    negative_unknown.append({
        "kind": "phase_unknown",
        "full_length_haplotype_phase_inferred": False,
        "independent_physical_molecules_assigned": False,
        "transitive_path_edges_emitted": False,
        "missing_insert_bases_imputed": False,
    })

    graph = {
        "schema_version": SCHEMA,
        "artifact_type": "shared_unphased_local_typed_graph",
        "sample": sample_name,
        "region": region,
        "mask_interval_zero_based_half_open": mask,
        "inputs": {
            "observation_169_sha256": observation_sha256,
            "local_node_manifest_170_sha256": local_manifest_sha256,
            "local_node_fasta_170_sha256": local_fasta_sha256,
            "direct_marker_v2_164_sha256": v2_sha256,
            "observation_schema": obs.get("schema_version"),
            "local_manifest_schema": manifest.get("schema_version"),
            "direct_v2_schema": v2.get("schema_version"),
        },
        "thresholds": {"min_joint_pairs": min_joint_pairs,
                       "min_consistent_signatures": min_consistent_signatures},
        "nodes": nodes,
        "edges": edges,
        "negative_unknown": negative_unknown,
        "safety": {
            "original_reads_fastq_modified": False,
            "original_micall_max_modified": False,
            "affects_198_acceptance": False,
            "affects_iva_baselines": False,
            "affects_reference_panel_or_gates": False,
            "independent_physical_molecules_claimed": False,
            "full_length_haplotype_phase_claimed": False,
            "transitive_inference_used": False,
            "missing_insert_bases_imputed": False,
        },
        "source_verification": {
            "externally_pinned_original_data_replayed": False,
            "empirical_use_permitted": False,
        },
        "interpretation": (
            "Typed local graph from supplied unphased observations; source trust is "
            "independently established by source_verification. Edges are tentative "
            "and local-only; same QNAME must observe both ends at Q15 with consistent unique "
            "paired signatures. No transitive paths, no haplotype assignment, no molecule "
            "duplication claims, no MAX/198/IVA/reference changes."
        ),
    }
    return graph

def _canonical_json(obj):
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"

def _private_write(path: Path, content: str, protected_roots):
    dest = Path(path).resolve()
    for root in protected_roots:
        r = Path(root).resolve()
        if dest == r or r in dest.parents:
            raise GraphBuildError(f"refusing output inside protected source: {r}")
    if dest.exists():
        raise GraphBuildError("refusing to overwrite existing output")
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--observation-json", type=Path, required=True)
    p.add_argument("--local-node-fasta", type=Path, required=True)
    p.add_argument("--local-node-manifest", type=Path, required=True)
    p.add_argument("--direct-v2-sidecar", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--expected-observation-sha256", required=True)
    p.add_argument("--expected-local-manifest-sha256", required=True)
    p.add_argument("--expected-local-fasta-sha256", required=True)
    p.add_argument("--expected-direct-v2-sha256", required=True)
    p.add_argument("--min-joint-pairs", type=int, default=5)
    p.add_argument("--min-consistent-signatures", type=int, default=5)
    p.add_argument("--sample", required=True)
    p.add_argument("--artifact-dir", type=Path, required=True)
    p.add_argument("--screen-ledger", type=Path, required=True)
    p.add_argument("--screen-sha256", required=True)
    p.add_argument("--original-fastq-r1", type=Path, required=True)
    p.add_argument("--original-fastq-r2", type=Path, required=True)
    p.add_argument("--depth", type=int, default=100)
    p.add_argument("--minimum-fraction", type=float, default=0.95)
    p.add_argument("--min-complete-signatures", type=int, default=20)
    p.add_argument("--protect-root", action="append", default=[], type=Path)
    args = p.parse_args(argv)
    def check(path, expected, label):
        actual = sha256_file(path)
        if expected and actual != expected:
            raise GraphBuildError(f"{label} SHA256 mismatch")
        return actual
    obs_sha = check(args.observation_json, args.expected_observation_sha256, "observation")
    man_sha = check(args.local_node_manifest, args.expected_local_manifest_sha256, "local manifest")
    fa_sha = check(args.local_node_fasta, args.expected_local_fasta_sha256, "local FASTA")
    v2_sha = check(args.direct_v2_sidecar, args.expected_direct_v2_sha256, "direct v2")
    obs = _load_json(args.observation_json)
    manifest = _load_json(args.local_node_manifest)
    attestation = replay_original_sources(args, obs, manifest)
    graph = build_graph(
        observation=obs,
        local_manifest=manifest,
        local_fasta_path=args.local_node_fasta,
        v2_sidecar=_load_json(args.direct_v2_sidecar),
        observation_sha256=obs_sha,
        local_manifest_sha256=man_sha,
        local_fasta_sha256=fa_sha,
        v2_sha256=v2_sha,
        min_joint_pairs=args.min_joint_pairs,
        min_consistent_signatures=args.min_consistent_signatures,
        sample=args.sample,
    )
    graph["source_verification"] = {
        "externally_pinned_original_data_replayed": True,
        "empirical_use_permitted": True,
        "original_micall_source_directory": str(args.artifact_dir.resolve()),
        "independent_cohort_screen_sha256": args.screen_sha256,
        "raw_original_mate_provenance_authenticated": True,
        "direct_link_source_verification": attestation["verification"],
    }
    protected = [args.observation_json.parent, args.local_node_fasta.parent,
                 args.local_node_manifest.parent, args.direct_v2_sidecar.parent,
                 args.artifact_dir, args.screen_ledger.parent,
                 args.original_fastq_r1.parent, args.original_fastq_r2.parent,
                 *args.protect_root]
    _private_write(args.output, _canonical_json(graph), protected)
    print(_canonical_json({
        "ok": True, "schema_version": SCHEMA, "output": str(args.output.resolve()),
        "sample": graph["sample"], "region": graph["region"],
        "nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
        "negative_unknown": len(graph["negative_unknown"]),
        "affects_198_acceptance": False,
    }), end="")

if __name__ == "__main__":
    try:
        main()
    except (GraphBuildError, ValueError, OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise SystemExit(f"ERROR: {e}")
