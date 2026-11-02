"""Retrieve the scoring references from the actual IVA MiCall container."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from podman_detached_lifecycle import run_detached


def load_micall_projects(iva_image):
    script = ("import importlib.resources as resources, sys; "
              "sys.stdout.buffer.write(resources.files('micall').joinpath('projects.json').read_bytes())")
    if os.environ.get('IVANKA_PODMAN_LIFECYCLE') == 'detached':
        # The IVA source catalog is immutable, but extraction is a genuine
        # Podman container too. Use the same serialized metadata path as
        # MiCall and the executable-binding verifier; never accept partial
        # logs or an uncertain Podman cleanup as authentic source material.
        name = (f'ivanka-bench-iva-{time.time_ns()}-{os.getpid()}-'
                f'{hashlib.sha256(iva_image.encode()).hexdigest()[:8]}')
        command = ['podman', 'run', '--rm', '--pull=never', '--name', name,
                   '--timeout', '598', '--stop-timeout', '2',
                   '--label', 'org.ottojung.ivanka.benchmark.role=reference-catalog',
                   '--entrypoint', 'python3', iva_image, '-c', script]
        with tempfile.TemporaryFile(mode='w+t', newline='') as stdout, tempfile.TemporaryFile(
                mode='w+t', newline='') as stderr:
            result = run_detached(command, stdout, stderr, remaining=600)
            if result.returncode:
                stderr.seek(0)
                raise RuntimeError(
                    f'IVA catalog extraction failed at Podman {result.stage}: '
                    f'{stderr.read()[-400:]}')
            stdout.seek(0)
            content = stdout.read().encode('utf-8')
    else:
        name = f'ivanka-reference-catalog-{os.getpid()}-{uuid.uuid4().hex[:12]}'
        command = ['podman', 'run', '--rm', '--pull=never', '--name', name,
                   '--label', 'org.ottojung.ivanka.benchmark.role=reference-catalog',
                   '--entrypoint', 'python3', iva_image, '-c', script]
        try:
            content = subprocess.check_output(command, timeout=600)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
            try:
                subprocess.run(['podman', 'rm', '--force', '--ignore', name],
                               check=True, capture_output=True, timeout=240)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as cleanup:
                raise RuntimeError(
                    f'IVA catalog extraction failed; container {name} may remain'
                ) from cleanup
            raise RuntimeError(f'IVA catalog extraction failed; removed {name}') from error
    expected = os.environ.get('IVANKA_PROJECTS_JSON')
    if expected and Path(expected).read_bytes() != content:
        raise ValueError('Project reference catalog does not match the IVA MiCall image')
    projects = json.loads(content)
    if (not isinstance(projects, dict) or
            not isinstance(projects.get('projects'), dict) or
            not isinstance(projects.get('regions'), dict)):
        raise ValueError('IVA MiCall image does not contain a valid projects.json catalog')
    return projects, hashlib.sha256(content).hexdigest()
