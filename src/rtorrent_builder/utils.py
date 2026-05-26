from __future__ import annotations

import re
from pathlib import Path


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
