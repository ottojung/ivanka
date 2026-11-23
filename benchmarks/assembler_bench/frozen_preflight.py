"""Read-only hard freeze preflight before any prospective Ivanka benchmark."""
import argparse
import json

from .frozen_contract import COMMIT, verify_source
from .frozen_receipts import attest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-root", required=True)
    parser.add_argument("--micall-source", required=True)
    parser.add_argument("--allow-reverted-tree", action="store_true",
                        help="Audit only: revert branch must never qualify as a source commit")
    args = parser.parse_args()
    results = attest(args.frozen_root)
    verify_source(args.micall_source, not args.allow_reverted_tree)
    results["required_common_micall_commit"] = COMMIT
    results["qualifying_source"] = not args.allow_reverted_tree
    print(json.dumps(results, sort_keys=True))


if __name__ == "__main__":
    main()
