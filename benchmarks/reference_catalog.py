"""Retrieve the scoring references from the actual IVA MiCall container."""
import hashlib
import json
import os
from pathlib import Path
import subprocess


def load_micall_projects(iva_image):
    script = ("import importlib.resources as resources, sys; "
              "sys.stdout.buffer.write(resources.files('micall').joinpath('projects.json').read_bytes())")
    content = subprocess.check_output(
        ['podman', 'run', '--rm', '--pull=never', '--entrypoint', 'python3',
         iva_image, '-c', script], timeout=120)
    expected = os.environ.get('IVANKA_PROJECTS_JSON')
    if expected and Path(expected).read_bytes() != content:
        raise ValueError('Project reference catalog does not match the IVA MiCall image')
    projects = json.loads(content)
    if (not isinstance(projects, dict) or
            not isinstance(projects.get('projects'), dict) or
            not isinstance(projects.get('regions'), dict)):
        raise ValueError('IVA MiCall image does not contain a valid projects.json catalog')
    return projects, hashlib.sha256(content).hexdigest()
