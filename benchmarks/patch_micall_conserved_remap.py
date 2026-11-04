#!/usr/bin/env python3
"""Install the conservative HCV remap experiment in a descendant MiCall image.

The original IVA image is never patched. Fail closed if MiCall's sam2aln
boundary is different from the pinned version validated by this experiment.
"""
import argparse
import importlib.util
from pathlib import Path
import shutil


LOG_MARKER = "        logger.info('Running sam2aln on %s.', self)"
INPUT_MARKER = "with open(with_prefix(self.remap_csv)) as remap_csv"
REPLACEMENT = "with open(_ivanka_remap_path) as remap_csv"
INJECTION = """        from micall.core.ivanka_conserved_remap import project_remap as _ivanka_project
        _original_remap = with_prefix(self.remap_csv)
        _remap_reference = with_prefix(self.remap_conseq_csv)
        _candidate_remap = _original_remap.with_name("ivanka-compatible-" + _original_remap.name)
        _ivanka_remap_path, _projection_info = _ivanka_project(
            _original_remap, _remap_reference, _candidate_remap)
        logger.info("Ivanka molecule-conserving remap: %s", _projection_info)
"""


def patched_source(source):
    if "ivanka_conserved_remap" in source:
        raise ValueError("MiCall already has the experimental patch")
    if source.count(LOG_MARKER) != 1 or source.count(INPUT_MARKER) != 1:
        raise ValueError("MiCall sam2aln interface changed; refusing patch")
    if source.find(LOG_MARKER) >= source.find(INPUT_MARKER):
        raise ValueError("unexpected MiCall remapping stage order")
    new = source.replace(LOG_MARKER, INJECTION + LOG_MARKER, 1)
    new = new.replace(INPUT_MARKER, REPLACEMENT, 1)
    compile(new, "<micall.drivers.sample experimental remap>", "exec")
    return new


def install(module_path):
    spec = importlib.util.find_spec("micall.drivers.sample")
    if spec is None or spec.origin is None:
        raise RuntimeError("MiCall Python package unavailable")
    sample = Path(spec.origin)
    output = sample.with_name(sample.name)
    # Compile and validate before modifying any installed MiCall file.
    new = patched_source(output.read_text())
    module_target = sample.parent.parent / "core" / "ivanka_conserved_remap.py"
    if module_target.exists():
        raise ValueError("experiment module already exists in target image")
    shutil.copyfile(module_path, module_target)
    output.write_text(new)
    print("Installed experimental paired-haplotype remap in", sample)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("module", type=Path)
    args = parser.parse_args()
    install(args.module)


if __name__ == "__main__":
    main()
