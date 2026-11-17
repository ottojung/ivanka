"""Read one Linux process tree's resident and proportional memory."""
from pathlib import Path
import os


def descendants(pid):
    pending = [pid]
    seen = set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        yield current
        try:
            children = Path(f"/proc/{current}/task/{current}/children").read_text()
            pending.extend(int(value) for value in children.split())
        except (OSError, ValueError):
            continue


def process_memory(pid):
    try:
        cells = Path(f"/proc/{pid}/statm").read_text().split()
        resident = int(cells[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return None
    proportional = None
    try:
        with Path(f"/proc/{pid}/smaps_rollup").open() as stream:
            for line in stream:
                if line.startswith("Pss:"):
                    proportional = int(line.split()[1]) * 1024
                    break
    except (OSError, ValueError, IndexError):
        pass
    return resident, proportional


def sample_tree(root):
    readings = [v for pid in descendants(root)
                if (v := process_memory(pid)) is not None]
    if not readings:
        return None
    pss = [value for _, value in readings]
    return (sum(rss for rss, _ in readings),
            sum(pss) if all(v is not None for v in pss) else None,
            len(readings))
