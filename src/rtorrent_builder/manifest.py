"""Manifest loading for rtorrent build variants using pydantic."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

import json5
from pydantic import TypeAdapter


def _load_jsonc_text(text: str) -> object:
    return json5.loads(text)


@dataclass(frozen=True, kw_only=True)
class GitHubTagSource:
    github: str
    tag_range: str
    url_template: str | None = None


@dataclass(frozen=True, kw_only=True)
class GitHubRefSource:
    github: str
    ref: str


@dataclass(frozen=True, kw_only=True)
class GitHubReleaseSource:
    github: str
    tag_range: str
    asset: str


@dataclass(frozen=True, kw_only=True)
class URLSource:
    url: str


@dataclass(frozen=True, kw_only=True)
class GitSource:
    url: str
    sha: str


PackageSource = GitHubTagSource | GitHubRefSource | GitHubReleaseSource | URLSource | GitSource


@dataclass(frozen=True, kw_only=True)
class LibInfo:
    source: PackageSource
    version: str = ""
    cxx_std: str | None = None
    requires: list[str] | None = None


@dataclass(frozen=True, kw_only=True)
class RawManifest:
    packages: dict[str, LibInfo]
    extends: str | list[str] | None = None
    executable_package: str | None = None
    target_glibc: str | None = None
    toolchain: str | None = None


@dataclass(frozen=True, kw_only=True)
class Manifest:
    variant: str
    packages: dict[str, LibInfo]
    target_glibc: str
    toolchain: str


@dataclass(frozen=True, kw_only=True)
class ResolvedPackage:
    url: str = ""
    version: str = ""
    cxx_std: str | None = None
    requires: list[str] | None = None
    src: GitSource | None = None

    def to_libinfo(self) -> LibInfo:
        if self.src is not None:
            return LibInfo(
                source=self.src,
                version=self.version,
                cxx_std=self.cxx_std,
                requires=self.requires,
            )
        return LibInfo(
            source=URLSource(url=self.url),
            version=self.version,
            cxx_std=self.cxx_std,
            requires=self.requires,
        )


@dataclass(frozen=True, kw_only=True)
class ResolvedManifest:
    variant: str
    packages: dict[str, ResolvedPackage]
    executable_package: str
    target_glibc: str
    toolchain: str


@dataclass(frozen=True, kw_only=True)
class LockFile:
    manifest_hash: str
    packages: dict[str, ResolvedPackage]
    executable_package: str
    target_glibc: str
    toolchain: str


@dataclass(frozen=True, kw_only=True)
class Lock:
    github: dict[str, str] = field(default_factory=dict)
    resolved_tags: dict[str, str] = field(default_factory=dict)
    manifest_hash: str | None = None

    def sha(self, github: str, ref: str) -> str | None:
        return self.github.get(f"{github}#{ref}")

    def resolved_tag(self, github: str, ref: str) -> str | None:
        return self.resolved_tags.get(f"{github}#{ref}")


_raw_manifest_adapter = TypeAdapter(RawManifest)
_manifest_adapter = TypeAdapter(Manifest)
_lock_adapter = TypeAdapter(Lock)
_lockfile_adapter = TypeAdapter(LockFile)


def load_lock(manifest_path: Path) -> Lock:
    lockfile = manifest_path.with_suffix(".lock")
    if lockfile.is_file():
        lock = _lock_adapter.validate_json(lockfile.read_text())
        if lock.manifest_hash is not None:
            current_hash = compute_manifest_hash(manifest_path)
            if lock.manifest_hash != current_hash:
                raise RuntimeError(
                    f"Manifest hash mismatch for {manifest_path.stem!r}: "
                    f"manifest changed since lock was generated. "
                    f"Run 'uv run python scripts/lock.py' to regenerate."
                )
        return lock
    return Lock()


def save_lock(lock: Lock, manifest_path: Path) -> None:
    lockfile = manifest_path.with_suffix(".lock")
    data: dict[str, object] = {"github": lock.github}
    if lock.resolved_tags:
        data["resolved_tags"] = lock.resolved_tags
    if lock.manifest_hash is not None:
        data["manifest_hash"] = lock.manifest_hash
    lockfile.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def compute_manifest_hash(manifest_path: Path) -> str:
    raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
    raw = _resolve_extends(raw, manifest_path.parent)
    payload: dict[str, object] = {
        "packages": asdict(raw)["packages"],
        "target_glibc": raw.target_glibc,
        "toolchain": raw.toolchain,
    }
    if raw.executable_package is not None:
        payload["executable_package"] = raw.executable_package
    content = json.dumps(payload, sort_keys=True, indent=None, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def _collect_lock_entries(manifest_path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
    raw = _resolve_extends(raw, manifest_path.parent)
    for pkg in raw.packages.values():
        if isinstance(pkg.source, GitHubRefSource):
            key = f"{pkg.source.github}#{pkg.source.ref}"
            entries[key] = pkg.source.ref
        elif isinstance(pkg.source, (GitHubTagSource, GitHubReleaseSource)):
            key = f"{pkg.source.github}#tag"
            entries[key] = ""
    return entries


def _collect_tag_range_entries(
    manifest_path: Path,
) -> dict[str, tuple[str, str]]:
    """Return {pkg_name: (repo#ref, tag_range)} for packages with tag_range."""
    raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
    raw = _resolve_extends(raw, manifest_path.parent)
    result: dict[str, tuple[str, str]] = {}
    for name, pkg in raw.packages.items():
        if isinstance(pkg.source, (GitHubTagSource, GitHubReleaseSource)):
            key = f"{pkg.source.github}#tag"
            result[name] = (key, pkg.source.tag_range)
    return result


def source_identity(pkg: LibInfo) -> str:
    if isinstance(pkg.source, GitHubTagSource):
        return f"github:{pkg.source.github}#tag={pkg.source.tag_range}"
    if isinstance(pkg.source, GitHubReleaseSource):
        return f"github:{pkg.source.github}#release={pkg.source.tag_range}"
    if isinstance(pkg.source, GitHubRefSource):
        return f"github:{pkg.source.github}#{pkg.source.ref}"
    if isinstance(pkg.source, URLSource):
        return f"url:{pkg.source.url}"
    raise ValueError("Package has no source")


def _validate_packages(packages: dict[str, LibInfo]) -> None:
    for name, pkg in packages.items():
        if isinstance(pkg.source, URLSource) and not pkg.version:
            raise ValueError(f"Package {name!r} with URL source requires a version")


def _resolve_extends(raw: RawManifest, manifests_dir: Path) -> RawManifest:
    extends = raw.extends
    if not extends:
        return raw
    if isinstance(extends, str):
        extends = [extends]

    merged_packages: dict[str, LibInfo] = {}
    merged_target_glibc: str | None = None
    merged_toolchain: str | None = None
    merged_executable_package: str | None = None

    for rel_path in extends:
        base_path = manifests_dir / rel_path
        base_raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(base_path.read_text()))
        base_raw = _resolve_extends(base_raw, manifests_dir)
        merged_packages |= base_raw.packages
        if base_raw.target_glibc is not None:
            merged_target_glibc = base_raw.target_glibc
        if base_raw.toolchain is not None:
            merged_toolchain = base_raw.toolchain
        if base_raw.executable_package is not None:
            merged_executable_package = base_raw.executable_package

    merged_packages |= raw.packages
    if raw.target_glibc is not None:
        merged_target_glibc = raw.target_glibc
    if raw.toolchain is not None:
        merged_toolchain = raw.toolchain
    if raw.executable_package is not None:
        merged_executable_package = raw.executable_package

    result_data: dict[str, object] = {
        "packages": merged_packages,
        "executable_package": merged_executable_package,
        "target_glibc": merged_target_glibc,
        "toolchain": merged_toolchain,
    }

    return _raw_manifest_adapter.validate_python(result_data)


_DEPENDENCIES: dict[str, list[str]] = {
    "zlib": [],
    "openssl": [],
    "brotli": [],
    "cares": [],
    "ncurses": [],
    "lua": [],
    "luajit": [],
    "nghttp2": ["zlib"],
    "libunistring": [],
    "libidn2": ["libunistring"],
    "curl": ["zlib", "openssl", "brotli", "cares", "zstd", "nghttp2", "libidn2"],
    "rtorrent-libtorrent": ["openssl", "zlib"],
    "boost": [],
    "libtorrent-rasterbar": ["boost", "openssl", "curl"],
    "zstd": [],
    "qt": ["zlib", "openssl", "zstd", "brotli"],
    "qttools": ["qt"],
    "qbittorrent": [
        "zlib",
        "openssl",
        "boost",
        "libtorrent-rasterbar",
        "qt",
        "qttools",
    ],
    "rtorrent": [
        "rtorrent-libtorrent",
    ],
    "rtorrent-meson": [
        "openssl",
        "zlib",
        "curl",
        "luajit",
    ],
}


def deps_for(name: str, packages: Mapping[str, LibInfo | ResolvedPackage]) -> list[str]:
    pkg = packages.get(name)
    if pkg and pkg.requires is not None:
        return pkg.requires
    return _DEPENDENCIES.get(name, [])


def reachable_packages(packages: Mapping[str, LibInfo | ResolvedPackage], root: str) -> set[str]:
    """Collect packages reachable from *root* via requires edges."""
    visited: set[str] = set()
    queue = [root]
    while queue:
        name = queue.pop()
        if name in visited:
            continue
        visited.add(name)
        for dep in deps_for(name, packages):
            if dep not in visited:
                queue.append(dep)
    return visited
