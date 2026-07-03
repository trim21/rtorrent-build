"""Persistent cross-build cache with Merkle-tree dependency hashing.

Each package's cache key includes its own identity (name, version, build
options) AND the hashes of all its transitive dependencies.  This means
changing a leaf dependency (e.g. openssl) invalidates only its subtree, while
unchanged subtrees remain cacheable.

Cache entries are uncompressed tarballs containing only the files that a
single package installed into the shared prefix, keyed by Merkle hash.  They
use the ``.cache`` file extension (not ``.tar``) to avoid being silently
dropped by GitHub Actions cache tooling.  Multiple cache entries can be
restored independently into the same prefix without conflict.

Compression is intentionally avoided because the cached files are mostly
compiled libraries (for which compression provides negligible savings) and
decompression overhead slows down cache restoration.

Each archive is accompanied by a .json metadata file recording the hash
computation inputs, so that cache-miss root causes can be diagnosed.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
import threading
from pathlib import Path

CACHE_EXT = ".cache"


def compute_merkle_hash(
    *,
    name: str,
    version: str,
    options: list[str],
    toolchain_name: str,
    zig_version: str,
    libc: str,
    arch: str,
    glibc_target: str,
    debug: bool,
    install_prefix: str,
    dep_hashes: dict[str, str],
) -> tuple[str, dict[str, object]]:
    """Compute a content-hash that uniquely identifies a package's build output.

    Returns (hash, payload) so callers can inspect or persist the inputs.
    """
    payload: dict[str, object] = {
        "name": name,
        "version": version,
        "options": options,
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
    return hashlib.sha256(raw.encode()).hexdigest(), payload


class CacheStore:
    """Manages a directory of cached per-package archives keyed by Merkle hash."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _pkg_dir(self, name: str) -> Path:
        return self.cache_dir / name

    def _archive_path(self, name: str, key: str) -> Path:
        return self._pkg_dir(name) / f"{key}{CACHE_EXT}"

    def _meta_path(self, name: str, key: str) -> Path:
        return self._pkg_dir(name) / f"{key}.json"

    def has(self, name: str, key: str) -> bool:
        return self._archive_path(name, key).exists()

    def restore(self, name: str, key: str, prefix: Path) -> bool:
        """Extract cached package files into *prefix*.  Returns True on success."""
        archive = self._archive_path(name, key)
        if not archive.exists():
            return False
        print(f"Persistent cache hit for {name}")
        prefix.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(archive, "r:*") as tf:
                tf.extractall(str(prefix))
        except (EOFError, tarfile.ReadError) as e:
            print(f"Corrupt cache file for {name}: {e}", file=sys.stderr)
            archive.unlink()
            meta = self._meta_path(name, key)
            if meta.exists():
                meta.unlink()
            return False
        return True

    def store_files(
        self,
        name: str,
        key: str,
        payload: dict[str, object],
        prefix: Path,
        relative_files: set[Path],
    ) -> None:
        """Create an uncompressed tarball and metadata JSON for *name* under *key*."""
        pkg_dir = self._pkg_dir(name)
        archive = self._archive_path(name, key)
        meta = self._meta_path(name, key)
        with self._lock:
            pkg_dir.mkdir(parents=True, exist_ok=True)
            if archive.exists():
                return
            print(f"Caching {name} ({len(relative_files)} files) -> {archive}")
            with tarfile.open(archive, "w:") as tf:
                for rel in sorted(relative_files):
                    abs_path = prefix / rel
                    if abs_path.exists():
                        tf.add(str(abs_path), arcname=str(rel))
            text = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
            meta.write_text(text)

    def diagnose_miss(self, name: str, current_payload: dict[str, object]) -> None:
        """When the current hash misses for *name*, check if earlier cached
        entries exist for the same package and print a diff of the hash inputs
        to help diagnose what changed.
        """
        pkg_dir = self._pkg_dir(name)
        if not pkg_dir.is_dir():
            return

        metas = sorted(pkg_dir.glob("*.json"))
        archives = sorted(pkg_dir.glob(f"*{CACHE_EXT}"))
        if not metas and not archives:
            return

        print(f"\n--- Cache miss diagnosis for {name} ---", file=sys.stderr)
        print(f"  pkg_dir: {pkg_dir}", file=sys.stderr)
        print(f"  contained: {[f.name for f in sorted(pkg_dir.iterdir())]}", file=sys.stderr)
        print("  Current hash inputs:", file=sys.stderr)
        for k, v in sorted(current_payload.items()):
            print(f"    {k}: {v!r}", file=sys.stderr)

        for mp in metas:
            try:
                stored = json.loads(mp.read_text())
            except (json.JSONDecodeError, OSError):
                print(f"  WARNING: could not read metadata {mp}", file=sys.stderr)
                continue
            archive_path = mp.with_suffix(CACHE_EXT)
            archive_exists = archive_path.exists()
            archive_size = archive_path.stat().st_size if archive_exists else 0
            print(f"\n  Cached entry: {mp.name}", file=sys.stderr)
            print(
                f"  Corresponding archive: {archive_path.name} "
                f"(exists={archive_exists}, size={archive_size})",
                file=sys.stderr,
            )
            print("  Cached hash inputs:", file=sys.stderr)
            all_keys = sorted(set(current_payload) | set(stored))
            for k in all_keys:
                cur = current_payload.get(k)
                old = stored.get(k)
                if cur != old:
                    print(f"    {k}: CURRENT={cur!r}  CACHED={old!r}", file=sys.stderr)
                else:
                    print(f"    {k}: {cur!r}  (unchanged)", file=sys.stderr)
        print(f"--- End cache miss diagnosis for {name} ---\n", file=sys.stderr)

    def gc(self, current_packages: dict[str, str]) -> int:
        """Remove cached archives not referenced by *current_packages*.

        *current_packages* is a mapping of ``{name: merkle_hash}`` for the
        current build.  Archives and metadata for other hashes (within each
        package directory) are removed.  Empty package directories are
        also removed.
        """
        removed = 0

        for entry in sorted(self.cache_dir.iterdir()):
            if entry.is_file():
                sfx = entry.suffix
                if sfx in (CACHE_EXT, ".json"):
                    print(f"Cache GC: removing stale old-format {entry}")
                    entry.unlink()
                    removed += 1
                    continue

            if not entry.is_dir():
                continue

            pkg_dir = entry
            current_key = current_packages.get(pkg_dir.name)

            for f in sorted(pkg_dir.glob(f"*{CACHE_EXT}")):
                key = f.stem
                if current_key is not None and key == current_key:
                    continue
                print(f"Cache GC: removing stale {f}")
                f.unlink()
                removed += 1
                meta = f.with_suffix(".json")
                if meta.exists():
                    meta.unlink()

            for m in sorted(pkg_dir.glob("*.json")):
                key = m.stem
                if current_key is not None and key == current_key:
                    continue
                m.unlink()

            remaining = list(pkg_dir.iterdir())
            if not remaining:
                pkg_dir.rmdir()

        return removed
