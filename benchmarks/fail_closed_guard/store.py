"""Pinned Podman store namespace shared by the watchdog and its readiness record."""
import tomllib
from pathlib import Path

from . import binding
from .errors import GuardExceeded

STORE_FORMAT = "{{.Store.GraphRoot}}"


def pin_env(env, *, storage_conf):
    """Bind Podman to the project store and discard inherited store config."""
    conf = Path(storage_conf)
    if conf.is_symlink() or not conf.is_file():
        raise GuardExceeded("binding_unavailable")
    pinned = dict(env or {})
    pinned.pop("CONTAINERS_CONF", None)
    pinned["CONTAINERS_STORAGE_CONF"] = str(conf)
    return pinned


def _configured_graphroot(conf):
    """Read [storage].graphroot from a real Podman TOML storage.conf.

    Podman storage.conf is TOML; quoted values must be parsed, not compared
    with their quotes. Duplicate keys/tables and malformed TOML fail closed.
    """
    try:
        with Path(conf).open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise GuardExceeded("store_namespace_mismatch") from exc
    if not isinstance(data, dict):
        raise GuardExceeded("store_namespace_mismatch")
    storage = data.get("storage")
    if not isinstance(storage, dict):
        raise GuardExceeded("store_namespace_mismatch")
    configured = storage.get("graphroot")
    if not isinstance(configured, str) or not configured:
        raise GuardExceeded("store_namespace_mismatch")
    return configured


def verify_namespace(env, expected, *, command=None):
    """Require both the pinned config and live Podman to name one store."""
    graphroot = str(expected)
    conf = Path(env.get("CONTAINERS_STORAGE_CONF", ""))
    if conf.is_symlink() or not conf.is_file():
        raise GuardExceeded("store_namespace_mismatch")
    configured = _configured_graphroot(conf)
    if configured != graphroot:
        raise GuardExceeded("store_namespace_mismatch")
    run = command or binding.command
    try:
        observed = run(["podman", "info", "--format", STORE_FORMAT], env).strip()
    except Exception as exc:
        raise GuardExceeded("inspection_unavailable") from exc
    if observed != graphroot:
        raise GuardExceeded("store_namespace_mismatch")
    return graphroot
