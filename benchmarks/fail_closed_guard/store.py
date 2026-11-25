"""Pinned Podman store namespace shared by the watchdog and its readiness record."""
import configparser
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


def verify_namespace(env, expected):
    """Require both the pinned config and live Podman to name one store."""
    graphroot = str(expected)
    conf = Path(env.get("CONTAINERS_STORAGE_CONF", ""))
    if conf.is_symlink() or not conf.is_file():
        raise GuardExceeded("store_namespace_mismatch")
    parser = configparser.ConfigParser()
    try:
        parser.read(str(conf))
        configured = parser.get("storage", "graphroot")
    except (configparser.Error, OSError) as exc:
        raise GuardExceeded("store_namespace_mismatch") from exc
    if configured != graphroot:
        raise GuardExceeded("store_namespace_mismatch")
    try:
        observed = binding.command(
            ["podman", "info", "--format", STORE_FORMAT], env).strip()
    except Exception as exc:
        raise GuardExceeded("inspection_unavailable") from exc
    if observed != graphroot:
        raise GuardExceeded("store_namespace_mismatch")
    return graphroot
