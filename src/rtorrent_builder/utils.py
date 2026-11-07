from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Generator
from pathlib import Path

from filelock import FileLock, Timeout


class BuildBusyError(RuntimeError):
    pass


@contextlib.contextmanager
def exclusive_build(lock_path: Path) -> Generator[None]:
    """Fail fast while another build in this checkout is still running.

    Concurrent builds would share the install prefix, the extracted sources and
    the download cache, so a second one corrupts the first rather than running
    in parallel. The lock is advisory and the kernel releases it if the process
    dies, so no stale-lock cleanup is needed.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(lock_path, timeout=0)
    try:
        lock.acquire()
    except Timeout:
        holder = lock_path.read_text().strip() or "unknown"
        raise BuildBusyError(
            f"Another build (pid {holder}) is already running in this checkout; "
            f"wait for it to finish before starting a second one ({lock_path})"
        ) from None
    try:
        lock_path.write_text(f"{os.getpid()}\n")
        yield
    finally:
        lock.release()


def conditional_args(specs: dict[str, bool]) -> list[str]:
    """Expand *specs* to args whose condition is enabled."""
    return [arg for arg, enabled in specs.items() if enabled]


def replace_in_file(
    path: Path, old: str | re.Pattern[str], new: str, *, required: bool = True
) -> None:
    """Replace *old* with *new* in *path*, verifying *old* exists first.

    Reads and writes in binary mode to preserve original line endings.
    Pass ``re.compile(...)`` for regex replacement, or a plain ``str`` for
    literal substring replacement.

    When *required* is False (default True), silently returns if *old* is
    not found instead of raising ValueError.
    """
    content = path.read_bytes().decode()
    if isinstance(old, re.Pattern):
        patched, count = re.subn(old, new, content)
        if count == 0:
            if required:
                raise ValueError(f"{old.pattern!r} not found in {path}")
            return
        path.write_bytes(patched.encode())
    else:
        if old not in content:
            if required:
                raise ValueError(f"{old!r} not found in {path}")
            return
        path.write_bytes(content.replace(old, new).encode())
