"""Independent check of the committed aggregate: controls byte-identical across
caps, no jackpot regression, receipts internally consistent. No truth opened.
"""
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).parent
AGG = json.loads((HERE / "aggregate.json").read_text())
RECEIPT = json.loads((HERE / "pinned_receipt.json").read_text())
CAPS = RECEIPT["caps_tested"]


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    checks = []
    cases = AGG["cases"]
    checks.append(("72_invocations", len(cases) == 72))
    checks.append(("all_exit_zero", all(c["exit_status"] == 0 for c in cases)))
    checks.append(("caps_16_24_32", CAPS == [16, 24, 32]))
    checks.append(("default_and_max_unchanged",
                   RECEIPT["default_cap_unchanged"] == 16
                   and RECEIPT["cli_maximum_unchanged"] == 1000))
    controls = sorted({c["case"] for c in cases
                       if c["case"].startswith(("equal_strains", "clonal"))})
    identical = []
    for case in controls:
        hashes = {c["output_sha256"] for c in cases if c["case"] == case}
        identical.append(len(hashes) == 1)
    checks.append((f"controls_identical_{sum(identical)}/{len(controls)}",
                   len(controls) == 8 and all(identical)))
    jack = {c["case"]: c for c in cases
            if c["case"].startswith("pcr_jackpot") and c["cap"] == 16}
    regressed = []
    improved_by_cap = {cap: 0 for cap in CAPS[1:]}
    for cap in CAPS[1:]:
        for case, base in jack.items():
            high = next(c for c in cases if c["case"] == case and c["cap"] == cap)
            if high["truth31_recovered"] < base["truth31_recovered"]:
                regressed.append(f"{case}|{cap}")
            if high["truth31_recovered"] > base["truth31_recovered"]:
                improved_by_cap[cap] += 1
    checks.append(("no_regressions", not regressed))
    for cap in CAPS[1:]:
        checks.append((f"improved_at_{cap}", improved_by_cap[cap] == 7))
    checks.append(("read_support_all_one",
                   all(c["contig_kmer_read_support_fraction"] == 1.0 for c in cases)))
    checks.append(("receipt_outputs_match_aggregate",
                   all(RECEIPT["output_sha256"][f"{c['case']}|{c['cap']}"]
                       == c["output_sha256"] for c in cases)))
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print("verify_digest", digest(json.dumps(checks, sort_keys=True)))
    if not all(ok for _, ok in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
