"""Manifest loading for rtorrent build variants using pydantic."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Annotated

import json5
from pydantic import Discriminator, Tag, TypeAdapter

from . import PROJECT_ROOT


def _load_jsonc_text(text: str) -> object:
    return json5.loads(text)


@dataclass(frozen=True, kw_only=True)
class URLSource:
    url: str


@dataclass(frozen=True, kw_only=True)
class GitSource:
    git: str
    ref: str


Source = Annotated[
    Annotated[URLSource, Tag("url")] | Annotated[GitSource, Tag("git")],
    Discriminator(lambda v: "git" if isinstance(v, dict) and "git" in v else "url"),
]


@dataclass(frozen=True, kw_only=True)
class LibInfo:
    source: Source
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
class Lock:
    git: dict[str, str] = field(default_factory=dict)
    manifest_hash: str | None = None

    def sha(self, git_url: str, ref: str) -> str | None:
        return self.git.get(f"{git_url}#{ref}")


_raw_manifest_adapter = TypeAdapter(RawManifest)
_manifest_adapter = TypeAdapter(Manifest)
_lock_adapter = TypeAdapter(Lock)


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
    data: dict[str, object] = {"git": lock.git}
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
        if isinstance(pkg.source, GitSource):
            key = f"{pkg.source.git}#{pkg.source.ref}"
            entries[key] = entries.get(key, "")
    return entries


def source_identity(pkg: LibInfo) -> str:
    if isinstance(pkg.source, GitSource):
        return f"git:{pkg.source.git}#{pkg.source.ref}"
    return f"url:{pkg.source.url}"


def _validate_packages(packages: dict[str, LibInfo]) -> None:
    for name, pkg in packages.items():
        if not isinstance(pkg.source, GitSource) and not pkg.version:
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


def load_manifest(variant: str, manifests_dir: Path | None = None) -> Manifest:
    """Load a build manifest for the given variant name."""
    if manifests_dir is None:
        manifests_dir = PROJECT_ROOT / "manifests"

    manifest_path = manifests_dir / f"{variant}.jsonc"
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}")
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    print(f"Loading manifest from {manifest_path}")
    raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
    raw = _resolve_extends(raw, manifests_dir)

    _validate_packages(raw.packages)

    if raw.target_glibc is None:
        raise ValueError(f"Manifest {variant!r} has no target_glibc")

    if raw.toolchain is None:
        raise ValueError(f"Manifest {variant!r} has no toolchain")

    return _manifest_adapter.validate_python(
        {
            "variant": variant,
            "packages": raw.packages,
            "target_glibc": raw.target_glibc,
            "toolchain": raw.toolchain,
        }
    )
