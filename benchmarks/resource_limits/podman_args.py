"""Pure source-frozen Podman argument transformations."""
CAP_BYTES = 4_000_000_000
CAP_SECONDS = 2400
PODMAN_TIMEOUT = 2398


def option(args, key):
    found = [i for i, v in enumerate(args) if v == key or v.startswith(key + "=")]
    if len(found) > 1:
        raise ValueError("duplicate Podman option " + key)
    if not found:
        return None, None
    i = found[0]
    if args[i] == key:
        if i + 1 >= len(args):
            raise ValueError("missing Podman option value: " + key)
        return i, args[i + 1]
    return i, args[i].split("=", 1)[1]


def set_option(args, key, value):
    i, _ = option(args, key)
    if i is None:
        return [args[0], key + "=" + str(value), *args[1:]]
    result = list(args)
    if args[i] == key:
        result[i + 1] = str(value)
    else:
        result[i] = key + "=" + str(value)
    return result


def capped(args):
    if not args or args[0] not in ("create", "run"):
        return list(args), False
    _, name = option(args, "--name")
    if not name or not name.startswith("ivanka-bench-"):
        return list(args), False
    _, timeout = option(args, "--timeout")
    if timeout is None or not timeout.isdecimal() or int(timeout) < 1:
        raise ValueError("MiCall benchmark must have positive Podman timeout")
    result = set_option(list(args), "--timeout", min(int(timeout), PODMAN_TIMEOUT))
    result = set_option(result, "--memory", CAP_BYTES)
    result = set_option(result, "--memory-swap", CAP_BYTES)
    return result, True
