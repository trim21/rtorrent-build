"""Manifest loading for rtorrent build variants using pydantic."""

import hashlib
import json
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


PackageSource = GitHubTagSource | GitHubRefSource | GitHubReleaseSource | URLSource


@dataclass(frozen=True, kw_only=True)
class LibInfo:
    source: PackageSource
    version: str = ""
    cxx_std: str | None = None


@dataclass(frozen=True, kw_only=True)
class RawManifest:
    packages: dict[str, LibInfo]
    extends: str | list[str] | None = None
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
    url: str
    version: str = ""
    cxx_std: str | None = None

    def to_libinfo(self) -> LibInfo:
        return LibInfo(
            source=URLSource(url=self.url),
            version=self.version,
            cxx_std=self.cxx_std,
        )


@dataclass(frozen=True, kw_only=True)
class ResolvedManifest:
    variant: str
    packages: dict[str, ResolvedPackage]
    target_glibc: str
    toolchain: str


@dataclass(frozen=True, kw_only=True)
class LockFile:
    manifest_hash: str
    packages: dict[str, ResolvedPackage]
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


def load_lock(manifests_dir: Path, variant: str) -> Lock:
    lockfile = manifests_dir / f"{variant}.lock"
    if lockfile.is_file():
        lock = _lock_adapter.validate_json(lockfile.read_text())
        if lock.manifest_hash is not None:
            manifest_path = manifests_dir / f"{variant}.jsonc"
            current_hash = compute_manifest_hash(manifest_path, manifests_dir)
            if lock.manifest_hash != current_hash:
                raise RuntimeError(
                    f"Manifest hash mismatch for {variant!r}: manifest changed since lock was "
                    f"generated. Run 'uv run python scripts/lock.py' to regenerate."
                )
        return lock
    return Lock()


def save_lock(lock: Lock, manifests_dir: Path, variant: str) -> None:
    lockfile = manifests_dir / f"{variant}.lock"
    data: dict[str, object] = {"github": lock.github}
    if lock.resolved_tags:
        data["resolved_tags"] = lock.resolved_tags
    if lock.manifest_hash is not None:
        data["manifest_hash"] = lock.manifest_hash
    lockfile.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def compute_manifest_hash(manifest_path: Path, manifests_dir: Path) -> str:
    raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
    raw = _resolve_extends(raw, manifests_dir)
    payload = {
        "packages": asdict(raw)["packages"],
        "target_glibc": raw.target_glibc,
        "toolchain": raw.toolchain,
    }
    content = json.dumps(payload, sort_keys=True, indent=None, ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


def _collect_lock_entries(manifest_path: Path, manifests_dir: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
    raw = _resolve_extends(raw, manifests_dir)
    for pkg in raw.packages.values():
        if isinstance(pkg.source, GitHubRefSource):
            key = f"{pkg.source.github}#{pkg.source.ref}"
            entries[key] = pkg.source.ref
        elif isinstance(pkg.source, (GitHubTagSource, GitHubReleaseSource)):
            key = f"{pkg.source.github}#tag"
            entries[key] = ""
    return entries


def _collect_tag_range_entries(
    manifest_path: Path, manifests_dir: Path
) -> dict[str, tuple[str, str]]:
    """Return {pkg_name: (repo#ref, tag_range)} for packages with tag_range."""
    raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
    raw = _resolve_extends(raw, manifests_dir)
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

    for rel_path in extends:
        base_path = manifests_dir / rel_path
        base_raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(base_path.read_text()))
        base_raw = _resolve_extends(base_raw, manifests_dir)
        merged_packages |= base_raw.packages
        if base_raw.target_glibc is not None:
            merged_target_glibc = base_raw.target_glibc
        if base_raw.toolchain is not None:
            merged_toolchain = base_raw.toolchain

    merged_packages |= raw.packages
    if raw.target_glibc is not None:
        merged_target_glibc = raw.target_glibc
    if raw.toolchain is not None:
        merged_toolchain = raw.toolchain

    return _raw_manifest_adapter.validate_python(
        {
            "packages": merged_packages,
            "target_glibc": merged_target_glibc,
            "toolchain": merged_toolchain,
        }
    )
