"""Derive current, independently checked per-arm samples from immutable MiCall files."""
import csv
import hashlib
import json
import math
from pathlib import Path

from .hxb2_preview import pinned_truth, sha, COHORT_SHA
from .public_case_metrics import synthetic as synthetic_metrics, physical as physical_metrics
from .resource_peak import peak_mib, physical_name, synthetic_name
from .resource_retry import select as select_retry

SYN_SCHEMA="ivanka.expanded.comparators_first_synthetic.v1"
REAL_SCHEMA="ivanka.expanded.comparators_first_real.v1"
PROGRESS_SCHEMA="ivanka.assembler-bench.active-progress.v1"
PANEL="018f6ab2e28a6abbbc2ba9dbaa522a42c8c45531276530a8956489f8e21cc4a8"
PHYSICAL_MANIFEST="4478ed222b4ace8f6b1c7eaa66d338ba14c4962c00b298089f8af48837169192"


def sha_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def freeze(path, expected_schema, images, proof, runner):
    file=Path(path)/"run_manifest.json"
    if not file.is_file():
        return None
    manifest=json.loads(file.read_text())
    if (manifest.get("schema")!=expected_schema
            or manifest.get("ivanka_deferred") is not True
            or manifest.get("original_seven_image_attestation",
                            manifest.get("original_seven_attestation_sha256"))!=sha(proof)
            or manifest.get("images")!={name:images[name] for name in images
                                       if name!="ivanka"}):
        raise ValueError("frozen six-assembler input/images changed")
    sources=manifest.get("sources_sha256",manifest.get("source_files_sha256"))
    if not isinstance(sources,dict) or not sources:
        raise ValueError("frozen benchmark sources absent")
    for name,digest in sources.items():
        candidates=[Path(runner)/"benchmarks"/part/name
                    for part in ("expanded","assembler_bench","")]
        match=next((p for p in candidates if p.is_file()),None)
        if match is None or sha(match)!=digest:
            raise ValueError("frozen executed source hash changed: "+name)
    return manifest


def sample(alias,tools,family=None):
    row={"alias":alias,"score":{t:None for t in tools},
         "seconds":{t:None for t in tools},"failures":[],
         "diagnostics":{t:{} for t in tools},
         "exact_profiles":{},"recovery":{},
         "floor_ok":None,"outcome":"incomplete"}
    if family is not None:
        row["family"]=family
    return row


def accept(row,tool,record,diagnostics):
    status=record["status"]
    if status=="success":
        score,seconds=record["score"],record["seconds"]
        budget=record.get("time_budget_seconds",1800)
        if (budget not in (1800,3000)
                or type(score) not in (int,float) or not math.isfinite(score)
                or score<0 or type(seconds) not in (int,float)
                or not math.isfinite(seconds) or not 0<seconds<=budget):
            raise ValueError("invalid source-scored final MiCall result")
        row["score"][tool]=score
        row["seconds"][tool]=seconds
        row["diagnostics"][tool]=diagnostics
    elif status=="failed":
        row["failures"].append(tool)
        row["diagnostics"][tool]=diagnostics
    else:
        raise ValueError("invalid terminal result")


def synth_arm(folder,tool,image):
    evidence=folder/"execution.json"
    if not evidence.exists():
        return None
    raw=json.loads(evidence.read_bytes())
    if (raw.get("sha256")!=image
            or raw.get("status") not in ("success","failed")
            or raw.get("score_origin")!="micall_final_max_reference_panel_v1"
            or raw.get("timing_origin")!="micall_in_container_monotonic_v1"
            or raw.get("argv",[]).count(image)!=1
            or raw.get("argv",[])[-1]!="--all_projects"):
        raise ValueError("unauthenticated synthetic MiCall output")
    argv=raw["argv"]
    if (argv.count("--timeout")!=1
            or argv[argv.index("--timeout")+1] not in ("1800","3000")
            or len([v for v in argv if v in ("--memory=4g","--memory=5g")])!=1):
        raise ValueError("unknown synthetic MiCall resource allocation")
    if (argv[argv.index("--timeout")+1]=="1800"
            and "--memory=4g" not in argv):
        raise ValueError("original synthetic memory allocation drift")
    if (argv[argv.index("--timeout")+1]=="3000"
            and "--memory=5g" not in argv):
        raise ValueError("new synthetic memory allocation drift")
    raw["time_budget_seconds"]=int(argv[argv.index("--timeout")+1])
    if raw["status"]=="success":
        output=raw.get("final_dominant",{})
        file=folder/output.get("source_output","nonexistent")
        if (raw.get("exit_code")!=0 or not file.is_file()
                or sha(file)!=output.get("conseq_csv_sha256")):
            raise ValueError("synthetic final MiCall output changed")
    return raw


def synthetic(root,images,proof,runner,resources=None):
    manifest=freeze(root,SYN_SCHEMA,images,proof,runner)
    if manifest is None:
        return {},None
    cohort,truth=pinned_truth()
    source=Path(root)
    if (manifest.get("expected")!=400
            or manifest.get("cohort_sha256")!=COHORT_SHA
            or manifest.get("truth_proof")!=truth):
        raise ValueError("synthetic HXB2 source manifest altered")
    rows={}
    for index,entry in enumerate(sorted(cohort["cases"],key=lambda c:c["id"]),1):
        ident=entry["id"]
        if not ident or "/" in ident or ".." in ident:
            raise ValueError("unsafe frozen synthetic case identifier")
        row=sample(f"H{index:03d}",images,ident.rsplit("-s",1)[0])
        for tool in images:
            if tool not in manifest["images"]:
                continue
            arm=synth_arm(source/ident/tool,tool,images[tool])
            if arm is not None:
                metrics=synthetic_metrics(arm)
                memory=peak_mib(resources or {},synthetic_name(arm))
                if memory is not None:
                    metrics["peak_ram_observed_mib"]=memory
                accept(row,tool,arm,metrics)
        if any(row["score"][t] is not None or t in row["failures"]
               for t in images):
            rows[ident]=row
    return rows,sha(source/"run_manifest.json")


def physical_pairs(witness_file,attestation_file):
    private=json.loads(Path(witness_file).read_text())
    anchor=json.loads(Path(attestation_file).read_text())
    pairs=private.get("samples")
    if (private.get("schema")!="ivanka.assembler-bench.verified-original-fastq-pairs.v1"
            or anchor.get("schema")!="ivanka.assembler-bench.authentic-physical-inputs.v1"
            or not isinstance(pairs,dict) or len(pairs)!=198
            or private.get("input_pairs_sha256")!=anchor.get("input_pairs_sha256")
            or sha_bytes(json.dumps(
                pairs,sort_keys=True,separators=(",",":")).encode())!=
                anchor.get("input_pairs_sha256")):
        raise ValueError("physical FASTQ witnesses differ from preflight")
    return pairs

def real_arm(source,tool,sample_name,image,pair,retries=None):
    path=source/tool/"checkpoints"/(sha_bytes(sample_name.encode())+".json")
    if not path.is_file():
        return None
    raw=json.loads(path.read_bytes())
    identifier=sha_bytes("".join(item["sha256"] for item in pair).encode())
    if raw.get("input_sha256")!=identifier:
        raise ValueError("physical MiCall original read pair differs")
    if (raw.get("sample")!=sample_name or raw.get("tool")!=tool
            or raw.get("image_id")!=image or raw.get("status")!="finished"
            or raw.get("reference_panel_sha256")!=PANEL
            or type(raw.get("failed")) is not bool):
        raise ValueError("unaligned physical MiCall source checkpoint")
    raw,recovery=select_retry(raw,path,retries,tool,sample_name,image)
    if (tool=="ivanka" and
            (raw.get("resource_timeout_seconds")!=3000 or recovery)):
        raise ValueError("deferred physical Ivanka must have its own 50m evidence")
    arm=raw.get("arm")
    if not isinstance(arm,dict) or arm.get("image_id")!=image:
        raise ValueError("physical MiCall image identity mismatch")
    evidence_root=Path(retries).resolve() if recovery else source
    budget=3000 if recovery or tool=="ivanka" else 1800
    provenance={"time_budget_seconds":budget,
                "container_name":physical_name(arm,tool,sample_name,sha_bytes),
                "recovery":recovery}
    if raw["failed"]:
        if raw.get("measurement") is not None:
            raise ValueError("failed physical arm cannot have a measured score")
        return {"status":"failed",**provenance}
    measure=raw.get("measurement")
    if (not isinstance(measure,dict) or arm.get("exit_code")!=0
            or measure.get("seconds")!=arm.get("seconds")):
        raise ValueError("physical MiCall timer evidence changed")
    artifact=Path(arm.get("artifact_dir","/"))
    if not artifact.is_relative_to(evidence_root/"artifacts"):
        raise ValueError("physical result escaped frozen artifact directory")
    metrics=(arm.get("metrics") or {}).get("outputs") or {}
    expected=(metrics.get("conseq.csv") or {}).get("sha256")
    if not (artifact/"conseq.csv").is_file() or sha(artifact/"conseq.csv")!=expected:
        raise ValueError("physical final consensus digest mismatch")
    return {"status":"success","score":measure["score"],
            "seconds":measure["seconds"],"metrics":arm.get("metrics",{}),
            **provenance}


def physical_tool_allowed(name, original_manifest):
    """The sixth-comparator manifest intentionally omitted deferred Ivanka."""
    return name in original_manifest["images"] or name == "ivanka"


def physical(root,data,images,proof,runner,witness_file,physical_attestation,
             resources=None,retries=None):
    manifest=freeze(root,REAL_SCHEMA,images,proof,runner)
    if manifest is None:
        return {},None
    if (manifest.get("expected_samples")!=198
            or manifest.get("reference_panel_sha256")!=PANEL
            or manifest.get("source_manifest_sha256")!=PHYSICAL_MANIFEST
            or sha(Path(data)/"manifest.tsv")!=PHYSICAL_MANIFEST):
        raise ValueError("physical cohort source or panel changed")
    with (Path(data)/"manifest.tsv").open(newline="") as stream:
        names=sorted(x["sample"] for x in csv.DictReader(stream,delimiter="\t"))
    if len(names)!=198 or len(set(names))!=198:
        raise ValueError("physical cohort not unique and complete")
    source=Path(root).resolve()
    pairs=physical_pairs(witness_file,physical_attestation)
    if set(pairs)!=set(names):
        raise ValueError("frozen cohort names differ from verified FASTQs")
    rows={}
    for index,name in enumerate(names,1):
        row=sample(f"R{index:03d}",images)
        for tool in images:
            # The original six-way manifest deliberately deferred Ivanka.
            # Its new physical stage uses the seventh independently pinned
            # image and the same 198 read pairs/reference panel. The arm
            # reader validates each final MAX output before publication.
            if not physical_tool_allowed(tool, manifest):
                continue
            arm=real_arm(source,tool,name,images[tool],pairs[name],retries)
            if arm is not None:
                metrics=physical_metrics(arm)
                memory=peak_mib(resources or {},arm.get("container_name"))
                if memory is not None:
                    metrics["peak_ram_observed_mib"]=memory
                accept(row,tool,arm,metrics)
                if arm.get("recovery"):
                    row["recovery"][tool]=arm["recovery"]
        if any(row["score"][t] is not None or t in row["failures"]
               for t in images):
            rows[name]=row
    return rows,sha(source/"run_manifest.json")
