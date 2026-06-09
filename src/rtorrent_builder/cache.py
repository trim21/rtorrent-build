"""Persistent cross-build cache with Merkle-tree dependency hashing.

Each package's cache key includes its own identity (name, version, url, build
options) AND the hashes of all its transitive dependencies.  This means
changing a leaf dependency (e.g. openssl) invalidates only its subtree, while
unchanged subtrees remain cacheable.

Cache entries are tarballs containing only the files that a single package
installed into the shared prefix, keyed by Merkle hash.  Multiple cache entries
can be restored independently into the same prefix without conflict.
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import threading
from pathlib import Path


def compute_merkle_hash(
    *,
    name: str,
    version: str,
    url: str,
    options: list[str],
    toolchain_name: str,
    zig_version: str,
    libc: str,
    arch: str,
    glibc_target: str,
    debug: bool,
    install_prefix: str,
    dep_hashes: dict[str, str],
) -> str:
    """Compute a content-hash that uniquely identifies a package's build output.

    The hash includes the package's own inputs plus the hashes of all
    dependencies (Merkle tree), so any change in a transitive dependency
    propagates upward.
    """
    payload: dict[str, object] = {
        "name": name,
        "version": version,
        "url": url,
        "options": sorted(options),
        "toolchain": toolchain_name,
        "zig": zig_version,
        "libc": libc,
        "arch": arch,
        "glibc_target": glibc_target,
        "debug": debug,
        "prefix": install_prefix,
        "deps": dict(sorted(dep_hashes.items())),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class CacheStore:
    """Manages a directory of cached per-package tarballs keyed by Merkle hash."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def has(self, key: str) -> bool:
        return (self.cache_dir / f"{key}.tar.gz").exists()

    def restore(self, key: str, prefix: Path, name: str) -> bool:
        """Extract cached package files into *prefix*.  Returns True on success."""
        archive = self.cache_dir / f"{key}.tar.gz"
        if not archive.exists():
            return False
        print(f"Cache hit: restoring {name} from {archive}")
        prefix.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(str(prefix))
        return True

    def store_files(self, key: str, prefix: Path, relative_files: set[Path], name: str) -> None:
        """Create a tarball of *relative_files* (relative to *prefix*) under *key*."""
        archive = self.cache_dir / f"{key}.tar.gz"
        with self._lock:
            if archive.exists():
                return
            print(f"Caching {name} ({len(relative_files)} files) -> {archive}")
            with tarfile.open(archive, "w:gz") as tf:
                for rel in sorted(relative_files):
                    abs_path = prefix / rel
                    if abs_path.exists():
                        tf.add(str(abs_path), arcname=str(rel))

    def gc(self, current_hashes: set[str]) -> int:
        """Remove cached tarballs not referenced by *current_hashes*."""
        removed = 0
        for f in sorted(self.cache_dir.glob("*.tar.gz")):
            key = f.stem
            if key not in current_hashes:
                print(f"Cache GC: removing stale {f}")
                f.unlink()
                removed += 1
        return removed
