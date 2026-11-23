"""Regenerate, validate, and render PX build definitions (no OCI execution)."""
import argparse
from pathlib import Path

from . import plan


def _validate_path(value):
    return Path(value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate")
    generate.add_argument("--registry", type=_validate_path, default=plan.REGISTRY)
    generate.add_argument("--output", type=_validate_path, default=plan.PLANS)

    validate = commands.add_parser("validate")
    validate.add_argument("--registry", type=_validate_path, default=plan.REGISTRY)
    validate.add_argument("--plans", type=_validate_path, default=plan.PLANS)

    render = commands.add_parser("render")
    render.add_argument("--tool", required=True)
    render.add_argument("--base-image-digest", required=True)
    render.add_argument("--tool-binary-sha256", required=True)
    render.add_argument("--adapter-checkout", required=True)
    render.add_argument("--registry-path", required=True)
    render.add_argument("--spades-binary-sha256", default=None)
    render.add_argument("--plans", type=_validate_path, default=plan.PLANS)

    args = parser.parse_args(argv)
    if args.command == "generate":
        document = plan.generate(args.registry)
        args.output.write_text(plan.dumps(document))
        print("wrote %s" % args.output)
    elif args.command == "validate":
        loaded = plan.validate_document(args.plans, args.registry)
        print("validation PASS: %d nonqualifying build plans" % len(loaded["builds"]))
    else:
        document = plan.validate_document(args.plans)
        extra = None
        if args.spades_binary_sha256 is not None:
            extra = {"SPADES_BINARY_SHA256": args.spades_binary_sha256}
        command = plan.render(document, args.tool, args.base_image_digest,
                              args.tool_binary_sha256, args.adapter_checkout,
                              args.registry_path, extra)
        print("\n".join(command))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
