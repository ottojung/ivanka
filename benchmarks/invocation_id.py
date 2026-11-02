"""Collision-resistant benchmark invocation identifiers."""
import os
import time
import uuid


def new_invocation_id():
    """Uniquely identify even simultaneous invocations in PID-reused containers."""
    return f"{int(time.time())}-{os.getpid()}-{uuid.uuid4().hex}"
