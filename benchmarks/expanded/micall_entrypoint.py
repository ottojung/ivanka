"""Common paired FASTQ CLI for competitor tools inside pinned MiCall images.

The image build installs a reviewed tool name in /etc/ivanka-expanded-tool
and binds this script to /usr/local/bin/ivanka. It never reads scoring truth.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

if __package__:
    from .adapters import ASSEMBLERS, execute, require_programs
else:
    # A pinned MiCall competitor image installs this file and adapters.py
    # side by side in /usr/local/bin.
    from adapters import ASSEMBLERS, execute, require_programs

TOOL_NAME = Path("/etc/ivanka-expanded-tool")


def run_tool(tool, reads1, reads2, output):
    if tool not in ASSEMBLERS or tool in ("ivanka", "iva"):
        raise ValueError("use packaged Ivanka and native IVA controls separately")
    binaries = require_programs(names=(tool,))
    with tempfile.TemporaryDirectory(prefix="expanded-micall-") as work:
        run = execute(tool, reads1, reads2, Path(work)/"assembler",
                      binaries, threads=2, timeout=1780)
        if run["status"] != "success":
            raise RuntimeError("competitor failed: " + str(run.get("error")))
        shutil.copyfile(run["fasta"], output)
        print("EXPANDED_MICALL_ASSEMBLER", tool, "tool_sha256",
              json.dumps(binaries[tool], sort_keys=True), file=sys.stderr)


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reads1", required=True, type=Path)
    parser.add_argument("--reads2", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args(args)
    tool = TOOL_NAME.read_text().strip()
    run_tool(tool, options.reads1, options.reads2, options.output)


if __name__ == "__main__":
    main()
