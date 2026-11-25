"""Lossless, fail-closed storage for retained scientific CSV tables.

Logical table names stay unchanged (``genome_coverage.csv``). A table may be
stored as the original plain bytes or as one zstd frame plus a proof sidecar
(``genome_coverage.csv.zst`` and ``genome_coverage.csv.zst.meta.json``).
Readers use :func:`find_table`, :func:`open_table` and :func:`logical_digest`,
which see one logical table regardless of how it is stored. The SHA-256 in the
proof sidecar is always the digest of the *uncompressed* original bytes, so
existing provenance that pins plain-byte digests remains valid after a table
is compressed.

Storage format (``ivanka-zstd-table/1``), chosen to be reproducible across the
two supported codec backends:

* exactly one zstd frame, compression level 3, nb_workers 1 (one thread);
* the frame carries a content checksum, so truncation and bit rot are detected;
* no dependence on a pledged content size or on a particular zstd build's byte
  stream -- readers rely only on the zstd frame contract and the checksum.

The portable codec is the ``backports.zstd`` package (the PEP 784 API backport)
declared in ``benchmarks/requirements.txt``. When it is unavailable, an
explicit ``zstd`` CLI (1.5.x) is used with ``-3 -T1 --check``, which produces
the same frame contract. Select with ``IVANKA_ZSTD_BACKEND=module|cli`` and set
the CLI location with ``IVANKA_ZSTD_PATH``.

Both a plain and a compressed variant may coexist only when each proves the
same uncompressed digest and size; any disagreement fails closed. Nothing in
this module runs an analysis, changes a measurement, or writes to a MiCall
source or container.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

FORMAT = "ivanka-zstd-table/1"
ZST_SUFFIX = ".zst"
META_SUFFIX = ".zst.meta.json"
ZSTD_LEVEL = 3
ZSTD_THREADS = 1
CHUNK = 1 << 16

# Large diagnostic tables are the compression population. Final consensus,
# contig and receipt-sized tables stay plain: external immutable consumers
# open those paths directly and were pinned before compression existed.
COMPRESSIBLE_TABLES = frozenset({
    "amino.csv",
    "clipping.csv",
    "concordance.csv",
    "concordance_detailed.csv",
    "exact_coverage.csv",
    "exact_coverage_overlapped.csv",
    "genome_coverage.csv",
    "multimap_depth.csv",
    "nuc.csv",
    "unstitched_genome_coverage.csv",
    "unstitched_multimap_depth.csv",
    "unique_aligned_fragments.csv",
    # Additional large non-scored diagnostic tables. A sealed migration must
    # still prove every logical digest and preserve consensus/receipt bytes.
    "amino_details.csv",
    "nuc_details.csv",
    "scratch_amino.csv",
    "scratch_nuc.csv",
    # Non-receipt-bound unstitched diagnostics. These are read-level /
    # per-position tables that no sealed receipt pins by SHA-256, no reader
    # opens through a hardcoded plain path, and none is a consensus, contig or
    # receipt-sized table. Allowing them here only permits lossless storage;
    # live conversion stays gated on operator authorization. The final
    # consensus, contig and receipt-sized tables are deliberately absent.
    "unstitched_amino.csv",
    "unstitched_amino_details.csv",
    "unstitched_cascade.csv",
    "unstitched_clipping.csv",
    "unstitched_concordance.csv",
    "unstitched_concordance_detailed.csv",
    "unstitched_concordance_seed.csv",
    "unstitched_coverage_scores.csv",
    "unstitched_coverage_summary.csv",
    "unstitched_failed.csv",
    "unstitched_failed_align.csv",
    "unstitched_insertions.csv",
    "unstitched_minimap_hits.csv",
    "unstitched_nuc.csv",
    "unstitched_nuc_details.csv",
    "unstitched_nuc_mutations.csv",
    "unstitched_remap_counts.csv",
    "unstitched_unique_aligned_fragments.csv",
})

_CLI_DEFAULT = ("/gnu/store/19576kzqs8adbvrq1b0c6ik8p01hs8ak-zstd-1.5.7"
                "/bin/zstd")


class TableError(Exception):
    """Base class for fail-closed table storage errors."""


class ConflictingVariants(TableError):
    """Plain and compressed variants disagree about the original bytes."""


class UnsupportedCodec(TableError):
    """A proof sidecar names a codec this reader does not implement."""


class MissingProof(TableError):
    """A compressed table has no proof sidecar and cannot be trusted."""


class InvalidProof(TableError):
    """Stored proof does not match the bytes it claims to describe."""


class TruncatedTable(InvalidProof):
    """The compressed stream ends before its zstd frame is complete."""


def _hash_stream(stream):
    digest, size = hashlib.sha256(), 0
    while True:
        block = stream.read(CHUNK)
        if not block:
            break
        digest.update(block)
        size += len(block)
    return digest.hexdigest(), size


def _hash_file(path):
    with Path(path).open("rb") as stream:
        return _hash_stream(stream)


def _read_chunks(stream):
    while True:
        block = stream.read(CHUNK)
        if not block:
            return
        yield block


def _backend():
    forced = os.environ.get("IVANKA_ZSTD_BACKEND", "").lower()
    if forced in ("module", "cli"):
        return forced
    try:
        import backports.zstd  # noqa: F401  (capability probe)
        return "module"
    except ImportError:
        return "cli"


def _cli_path():
    configured = os.environ.get("IVANKA_ZSTD_PATH")
    if configured:
        return configured
    if Path(_CLI_DEFAULT).is_file():
        return _CLI_DEFAULT
    found = shutil.which("zstd")
    if found:
        return found
    raise TableError("no zstd codec: install backports-zstd or the zstd CLI")


def _compress_module(source, target):
    from backports.zstd import CompressionParameter, ZstdCompressor
    options = {CompressionParameter.compression_level: ZSTD_LEVEL,
               CompressionParameter.nb_workers: ZSTD_THREADS,
               CompressionParameter.checksum_flag: True}
    compressor = ZstdCompressor(options=options)
    for block in _read_chunks(source):
        target.write(compressor.compress(block, compressor.CONTINUE))
    target.write(compressor.flush(compressor.FLUSH_FRAME))


def _compress_cli(source, target):
    with subprocess.Popen(
            [_cli_path(), "-q", "-%d" % ZSTD_LEVEL, "-T%d" % ZSTD_THREADS,
             "--check", "-c"],
            stdin=subprocess.PIPE, stdout=target,
            stderr=subprocess.PIPE) as process:
        for block in _read_chunks(source):
            process.stdin.write(block)
        process.stdin.close()
        error = process.stderr.read().decode("utf-8", "replace")
        if process.wait():
            raise TableError("zstd compression failed: " + error.strip())


def _decompress_module(path):
    from backports.zstd import ZstdDecompressor
    decoder = ZstdDecompressor()
    with path.open("rb") as source:
        for block in _read_chunks(source):
            if decoder.eof:
                raise InvalidProof("bytes follow the zstd frame: " + path.name)
            output = decoder.decompress(block, CHUNK)
            if output:
                yield bytes(output)
            while not decoder.needs_input and not decoder.eof:
                output = decoder.decompress(b"", CHUNK)
                if output:
                    yield bytes(output)
    if not decoder.eof:
        raise TruncatedTable("incomplete zstd frame: " + path.name)
    if getattr(decoder, "unused_data", b""):
        raise InvalidProof("bytes follow the zstd frame: " + path.name)


def _decompress_cli(path):
    with tempfile.TemporaryFile() as plain:
        with path.open("rb") as source:
            with subprocess.Popen(
                    [_cli_path(), "-q", "-d", "-c"], stdin=source,
                    stdout=plain, stderr=subprocess.PIPE) as process:
                error = process.stderr.read().decode("utf-8", "replace")
                if process.wait():
                    raise TruncatedTable("zstd decode failed: "
                                         + error.strip())
        plain.seek(0)
        yield from _read_chunks(plain)


def _decompress_chunks(path):
    yield from (_decompress_module(path) if _backend() == "module"
                else _decompress_cli(path))


def _containment_ok(logical):
    # Ensure the logical path resolves under its logical parent directory.
    # Reject if any parent component is a symlink by requiring the resolved
    # parent to be the same as the logical parent's resolved form.
    logical = Path(logical)
    parent = logical.parent
    try:
        if parent.exists():
            # Any symlink in parent chain makes resolution ambiguous/redirecting.
            for part in [parent, *parent.parents]:
                if part.is_symlink():
                    raise InvalidProof("refusing symlinked parent path: " + logical.name)
        resolved_parent = parent.resolve()
        resolved_logical = (resolved_parent / logical.name)
        # If the logical file exists, its realpath must be that resolved path
        # (no symlink was involved). We already rejected symlinks above; also
        # confirm the resolved target is inside resolved_parent.
        if logical.exists():
            real = logical.resolve()
            try:
                real.relative_to(resolved_parent)
            except ValueError:
                raise InvalidProof("table path escapes parent directory: " + logical.name)
        return resolved_logical
    except InvalidProof:
        raise
    except OSError as exc:
        raise InvalidProof("cannot resolve table path: " + logical.name) from exc


def _paths(path):
    logical = Path(path)
    # Reject symlinked parents/files early and pin to resolved containment.
    _containment_ok(logical)
    plain = logical
    compressed = logical.with_name(logical.name + ZST_SUFFIX)
    meta_path = logical.with_name(logical.name + META_SUFFIX)
    for p in (plain, compressed, meta_path):
        if p.exists() and p.is_symlink():
            raise InvalidProof("refusing symlinked table path: " + p.name)
    return (plain, compressed, meta_path)


def find_table(*candidates):
    """Return the first candidate stored as a plain or compressed table."""
    for candidate in candidates:
        plain, compressed, _ = _paths(candidate)
        if plain.is_file() or compressed.is_file():
            return plain
    return None


def load_meta(meta_path):
    path = Path(meta_path)
    if not path.is_file():
        raise MissingProof("no compression proof sidecar: " + path.name)
    try:
        proof = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InvalidProof("unreadable compression proof: " + path.name) from exc
    if proof.get("format") != FORMAT:
        raise InvalidProof("unknown table format: " + path.name)
    if proof.get("codec") != "zstd":
        raise UnsupportedCodec("unsupported codec in " + path.name)
    if (proof.get("level") != ZSTD_LEVEL or proof.get("threads") != ZSTD_THREADS
            or proof.get("checksum") is not True):
        raise InvalidProof("codec parameters differ from " + FORMAT)
    for field in ("original_sha256", "compressed_sha256"):
        value = proof.get(field)
        if not isinstance(value, str) or len(value) != 64:
            raise InvalidProof("invalid %s in %s" % (field, path.name))
    for field in ("original_size", "compressed_size"):
        value = proof.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise InvalidProof("invalid %s in %s" % (field, path.name))
    return proof


def _verify_compressed(path, proof):
    digest, size = _hash_file(path)
    if (digest != proof["compressed_sha256"]
            or size != proof["compressed_size"]):
        raise InvalidProof("compressed bytes changed: " + path.name)


def _digest_decompressed(path, proof):
    digest, size = hashlib.sha256(), 0
    for block in _decompress_chunks(path):
        digest.update(block)
        size += len(block)
    if (digest.hexdigest() != proof["original_sha256"]
            or size != proof["original_size"]):
        raise InvalidProof("decompressed bytes differ from proof: " + path.name)
    return digest.hexdigest(), size


def _assert_equivalent(plain, compressed, meta_path):
    proof = load_meta(meta_path)
    _verify_compressed(compressed, proof)
    plain_hash, plain_size = _hash_file(plain)
    compressed_hash, compressed_size = _digest_decompressed(compressed, proof)
    expected = (proof["original_sha256"], proof["original_size"])
    if ((plain_hash, plain_size) != expected
            or (compressed_hash, compressed_size) != expected):
        raise ConflictingVariants("plain and compressed tables disagree: "
                                  + plain.name)


def logical_digest(path):
    """Return ``(sha256, size)`` of the logical uncompressed table bytes."""
    plain, compressed, meta_path = _paths(path)
    has_plain, has_compressed = plain.is_file(), compressed.is_file()
    if has_plain and has_compressed:
        _assert_equivalent(plain, compressed, meta_path)
        return _hash_file(plain)
    if has_compressed:
        proof = load_meta(meta_path)
        _verify_compressed(compressed, proof)
        return _digest_decompressed(compressed, proof)
    if has_plain:
        return _hash_file(plain)
    raise FileNotFoundError(str(plain))


def open_table(path, *, newline="", encoding="utf-8", errors=None):
    """Open a logical table as text, transparently decoding a compressed one."""
    plain, compressed, meta_path = _paths(path)
    has_plain, has_compressed = plain.is_file(), compressed.is_file()
    if has_plain and has_compressed:
        _assert_equivalent(plain, compressed, meta_path)
    if has_compressed:
        proof = load_meta(meta_path)
        _verify_compressed(compressed, proof)
        stream = _VerifiedText(compressed, proof, newline=newline,
                               encoding=encoding, errors=errors)
        return stream
    if has_plain:
        return plain.open("r", newline=newline, encoding=encoding, errors=errors)
    raise FileNotFoundError(str(plain))


class _VerifiedText(io.TextIOWrapper):
    """Text wrapper whose underlying raw stream checks the proof at EOF."""

    def __init__(self, compressed, proof, *, newline, encoding, errors):
        super().__init__(_ProofRaw(compressed, proof), encoding=encoding,
                         newline=newline, errors=errors)


class _ProofRaw(io.RawIOBase):
    def __init__(self, compressed, proof):
        self._blocks = iter(_decompress_chunks(compressed))
        self._digest = hashlib.sha256()
        self._size = 0
        self._buffer = b""
        self._proof = proof
        self._proof_checked = False
        self._had_error = False

    def readable(self):
        return True

    def readinto(self, target):
        view = memoryview(target)
        filled = 0
        try:
            while filled < len(view):
                if not self._buffer:
                    try:
                        self._buffer = next(self._blocks)
                    except StopIteration:
                        self._check_proof()
                        break
                take = min(len(view) - filled, len(self._buffer))
                view[filled:filled + take] = self._buffer[:take]
                self._buffer = self._buffer[take:]
                filled += take
                self._digest.update(view[:take].tobytes())
                self._size += take
        except Exception:
            self._had_error = True
            raise
        return filled

    def _check_proof(self):
        if (self._digest.hexdigest() != self._proof["original_sha256"]
                or self._size != self._proof["original_size"]):
            raise InvalidProof("decompressed content differs from proof")
        self._proof_checked = True

    def close(self):
        if self.closed:
            return
        try:
            if not self._proof_checked and not self._had_error:
                # Callers such as header-only consumers may close early. Drain
                # the remaining decompressed stream in bounded chunks so the
                # proof still covers every byte and trailing/corrupt data fails.
                self._digest.update(self._buffer)
                self._size += len(self._buffer)
                self._buffer = b""
                for block in self._blocks:
                    self._digest.update(block)
                    self._size += len(block)
                self._check_proof()
        finally:
            try:
                self._blocks.close()
            finally:
                super().close()


def _fsync_dir(directory):
    try:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass


def compress_table(path, *, keep_plain=False):
    """Atomically replace one plain diagnostic table by a verified compressed pair.

    Re-running after a completed or interrupted attempt is idempotent: an
    already-proven compressed pair is returned without rewriting it. The plain
    file is removed only after the compressed bytes, their proof and a full
    decompressed readback have all been verified and durably installed.
    """
    plain, compressed, meta_path = _paths(path)
    if plain.name not in COMPRESSIBLE_TABLES:
        raise ValueError("table is not in the compression population: "
                         + plain.name)
    if compressed.is_file() and meta_path.is_file():
        proof = load_meta(meta_path)
        _verify_compressed(compressed, proof)
        _digest_decompressed(compressed, proof)
        if plain.is_file():
            digest, size = _hash_file(plain)
            if (digest, size) != (proof["original_sha256"],
                                  proof["original_size"]):
                raise ConflictingVariants("plain table changed before "
                                          + plain.name)
            if not keep_plain:
                plain.unlink()
        return compressed
    if compressed.is_file() and not plain.is_file():
        raise MissingProof("incomplete compression has no plain source: "
                           + plain.name)

    if not plain.is_file():
        raise FileNotFoundError(str(plain))
    original_digest, original_size = _hash_file(plain)
    folder = plain.parent
    handle, temp_name = tempfile.mkstemp(prefix=compressed.name + ".tmp.",
                                         dir=folder)
    os.close(handle)
    temp_compressed = Path(temp_name)
    try:
        with temp_compressed.open("wb") as target:
            with plain.open("rb") as source:
                if _backend() == "module":
                    _compress_module(source, target)
                else:
                    _compress_cli(source, target)
        compressed_digest, compressed_size = _hash_file(temp_compressed)
        proof = {"format": FORMAT, "codec": "zstd", "level": ZSTD_LEVEL,
                 "threads": ZSTD_THREADS, "checksum": True,
                 "original_name": plain.name,
                 "original_sha256": original_digest,
                 "original_size": original_size,
                 "compressed_sha256": compressed_digest,
                 "compressed_size": compressed_size}
        _verify_compressed(temp_compressed, proof)
        readback_digest, readback_size = _digest_decompressed(
            temp_compressed, proof)
        if (readback_digest, readback_size) != (original_digest, original_size):
            raise InvalidProof("compressed readback differs from plain "
                               + plain.name)
        handle, meta_temp_name = tempfile.mkstemp(
            prefix=meta_path.name + ".tmp.", dir=folder)
        with os.fdopen(handle, "w", encoding="utf-8") as target:
            json.dump(proof, target, sort_keys=True, indent=2)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        meta_temp = Path(meta_temp_name)
        try:
            os.replace(temp_compressed, compressed)
            os.replace(meta_temp, meta_path)
            _fsync_dir(folder)
        finally:
            meta_temp.unlink(missing_ok=True)
    finally:
        temp_compressed.unlink(missing_ok=True)
    if not keep_plain:
        plain.unlink()
    return compressed
