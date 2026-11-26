"""Prepare and attest an isolated Podman store that reuses archived image layers.

This is a preflight, not a runtime resource guard or a benchmark result.
The archived source must be protected from writes and retirement by its owner.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

SCHEMA = "ivanka.podman-readonly-store.v1"
SHA = re.compile(r"[0-9a-f]{64}")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def absolute(path, *, exists=True):
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=exists) != path:
        raise ValueError("store paths must be absolute and not symlinked")
    if exists and not path.is_dir():
        raise ValueError("store path is not a directory")
    return path


def source_state(source, image, manifest):
    if not SHA.fullmatch(image) or not SHA.fullmatch(manifest):
        raise ValueError("exact config and manifest SHA256 required")
    metadata = source / "overlay-images" / "images.json"
    image_manifest = source / "overlay-images" / image / "manifest"
    for path in (metadata, image_manifest):
        if path.resolve(strict=True) != path or not path.is_file():
            raise ValueError("source metadata must be a plain file")
    raw = image_manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest:
        raise ValueError("archived source manifest differs from pin")
    if json.loads(raw)["config"]["digest"] != "sha256:" + image:
        raise ValueError("archived manifest names a different image")
    return {"source_metadata_sha256": digest(metadata),
            "source_manifest_sha256": manifest}


def config_text(source, namespace):
    def quote(path):
        return json.dumps(str(path), ensure_ascii=False)
    return ("[storage]\ndriver = \"overlay\"\n"
            f"graphroot = {quote(namespace / 'store')}\n"
            f"runroot = {quote(namespace / 'run')}\n"
            "[storage.options]\n"
            f"additionalimagestores = [{quote(source)}]\n")


def command(config, args, run):
    env = {**os.environ, "CONTAINERS_STORAGE_CONF": str(config)}
    try:
        result = run(["podman", "--remote=false", *args], env=env,
                     capture_output=True, text=True, check=True, timeout=60)
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValueError("Podman reuse inspection failed") from exc


def inspect(config, namespace, image, manifest, run):
    store = command(config, ["info", "--format", "json"], run)["store"]
    if (store["graphRoot"], store["runRoot"], store["graphDriverName"]) != (
            str(namespace / "store"), str(namespace / "run"), "overlay"):
        raise ValueError("Podman addressed the wrong store")
    listing = command(config, ["images", "-a", "--no-trunc", "--format", "json"], run)
    matches = [row for row in listing if row["Id"].removeprefix("sha256:") == image]
    if not matches or any(row["ReadOnly"] is not True for row in matches):
        raise ValueError("image is absent or locally writable")
    result = command(config, ["image", "inspect", image], run)
    if len(result) != 1:
        raise ValueError("ambiguous image inspection")
    detail = result[0]
    layers = detail["RootFS"]["Layers"]
    if (detail["Id"].removeprefix("sha256:") != image
            or detail["Digest"] != "sha256:" + manifest
            or not layers or not all(re.fullmatch(r"sha256:[0-9a-f]{64}", x) for x in layers)):
        raise ValueError("reused image identity differs from pin")
    return {"image_id": image, "manifest_sha256": manifest, "layers": layers,
            "podman_read_only": True}


def verify(source, namespace, image, manifest, run=subprocess.run):
    source, namespace = absolute(source), absolute(namespace)
    if (source == namespace or source in namespace.parents
            or namespace in source.parents):
        raise ValueError("source and writable namespace must be disjoint")
    for name in ("store", "run"):
        absolute(namespace / name)
    config = namespace / "storage.conf"
    if config.resolve(strict=True) != config or not config.is_file():
        raise ValueError("reuse configuration is not a plain file")
    if config.read_text() != config_text(source, namespace):
        raise ValueError("reuse configuration differs from expected store")
    before = source_state(source, image, manifest)
    result = inspect(config, namespace, image, manifest, run)
    if source_state(source, image, manifest) != before:
        raise ValueError("archived source changed during preflight")
    return {"schema": SCHEMA, "source": str(source), "namespace": str(namespace),
            "config_sha256": digest(config), **before, **result}


def prepare(source, namespace, image, manifest, run=subprocess.run):
    source = absolute(source)
    namespace = absolute(namespace, exists=False)
    if source == namespace or source in namespace.parents or namespace in source.parents:
        raise ValueError("source and writable namespace must be disjoint")
    source_state(source, image, manifest)
    absolute(namespace.parent)
    namespace.mkdir(mode=0o700)
    for name in ("store", "run"):
        (namespace / name).mkdir(mode=0o700)
    config = namespace / "storage.conf"
    with config.open("x") as handle:
        handle.write(config_text(source, namespace))
    result = verify(source, namespace, image, manifest, run)
    with (namespace / "reuse-receipt.json").open("x") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return result

def readback(source, namespace, image, manifest, run=subprocess.run):
    result = verify(source, namespace, image, manifest, run)
    receipt = Path(namespace) / "reuse-receipt.json"
    if receipt.resolve(strict=True) != receipt or not receipt.is_file():
        raise ValueError("reuse receipt is not a plain file")
    if result != json.loads(receipt.read_text()):
        raise ValueError("reuse receipt no longer matches source and store")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--namespace", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    action = prepare if args.action == "prepare" else readback
    result = action(args.source, args.namespace, args.image, args.manifest)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
