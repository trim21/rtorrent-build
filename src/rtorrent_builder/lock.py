"""Lock file generation: resolves git sources to URL-only manifests."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from . import PROJECT_ROOT
from .manifest import (
    GitHubRefSource,
    GitHubReleaseSource,
    GitHubTagSource,
    LibInfo,
    PackageSource,
    ResolvedManifest,
    URLSource,
    _load_jsonc_text,
    _lockfile_adapter,
    _raw_manifest_adapter,
    _resolve_extends,
    compute_manifest_hash,
)
from .version_range import resolve_best

_VERSION_PATTERNS: dict[str, str] = {
    "boostorg/boost": r"^boost-(\d+)\.(\d+)\.(\d+)$",
    "curl/curl": r"^curl-(\d+)_(\d+)_(\d+)$",
    "openssl/openssl": r"^openssl-(\d+)\.(\d+)\.(\d+)$",
    "qbittorrent/qBittorrent": r"^release-(\d+)\.(\d+)\.(\d+)$",
}


def _gh_tags(owner_repo: str) -> list[str]:
    """Fetch tags from GitHub using git ls-remote (no API token needed)."""
    url = f"https://github.com/{owner_repo}.git"
    result = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", url],
        capture_output=True,
        text=True,
        check=True,
    )
    tags: list[str] = []
    for line in result.stdout.splitlines():
        _sha, ref = line.split()
        tags.append(ref.removeprefix("refs/tags/"))
    return tags


def _extract_version(tag: str, repo: str | None = None) -> str | None:
    r"""Extract version number from a tag.

    When *repo* is given and present in ``_VERSION_PATTERNS``, the
    corresponding regex is used (capture groups are joined with dots).
    Otherwise only tags like ``v1.2.3`` or ``1.2.3`` are accepted.
    """
    if repo and repo in _VERSION_PATTERNS:
        m = re.search(_VERSION_PATTERNS[repo], tag)
        if m:
            return ".".join(m.groups())
        return None
    m = re.match(r"^v?(\d+\.\d+(?:\.\d+)?)$", tag)
    return m.group(1) if m else None


def _resolve_ref(owner_repo: str, ref: str) -> str:
    url = f"https://github.com/{owner_repo}.git"
    result = subprocess.run(
        ["git", "ls-remote", url, ref],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        sha, name = line.split()
        if name == ref or name == f"refs/heads/{ref}" or name == f"refs/tags/{ref}":
            return sha
    raise ValueError(f"Ref {ref} not found in {owner_repo}")


def _resolve_github_source(source: PackageSource) -> tuple[str, str]:
    """Resolve a GitHub source to (url, version)."""
    if isinstance(source, GitHubRefSource):
        sha = _resolve_ref(source.github, source.ref)
        url = f"https://github.com/{source.github}/archive/{sha}.tar.gz"
        return url, sha[:12]
    if isinstance(source, (GitHubTagSource, GitHubReleaseSource)):
        tags = _gh_tags(source.github)
        versions = [(t, _extract_version(t, source.github)) for t in tags]
        version_strings = [v for _, v in versions if v]
        if not version_strings:
            raise ValueError(f"No version tags found for {source.github}")
        best = resolve_best(version_strings, source.tag_range)
        tag = next(t for t, v in versions if v == best)
        if isinstance(source, GitHubReleaseSource):
            asset = source.asset.format(version=best)
            url = f"https://github.com/{source.github}/releases/download/{tag}/{asset}"
        else:
            url = f"https://github.com/{source.github}/archive/refs/tags/{tag}.tar.gz"
        return url, best
    raise TypeError(f"Unsupported git source type: {type(source)}")


def _resolve_source(pkg_name: str, lib: LibInfo) -> tuple[URLSource, str]:
    """Resolve a LibInfo's source to (URL-only source, version)."""
    if isinstance(lib.source, URLSource):
        return lib.source, lib.version
    if isinstance(lib.source, (GitHubRefSource, GitHubTagSource, GitHubReleaseSource)):
        url, version = _resolve_github_source(lib.source)
        return URLSource(url=url), version
    raise ValueError(f"Package {pkg_name!r} has no source")


def resolve_manifest(variant: str, manifests_dir: Path | None = None) -> None:
    """Resolve a manifest to a URL-only lock file."""
    if manifests_dir is None:
        manifests_dir = PROJECT_ROOT / "manifests"

    manifest_path = manifests_dir / f"{variant}.jsonc"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    print(f"Resolving {variant}...")
    raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
    raw = _resolve_extends(raw, manifests_dir)

    resolved_packages: dict[str, dict] = {}
    for name, pkg in raw.packages.items():
        url_source, version = _resolve_source(name, pkg)
        entry: dict = {"url": url_source.url}
        if version:
            entry["version"] = version
        if pkg.cxx_std:
            entry["cxx_std"] = pkg.cxx_std
        resolved_packages[name] = entry
        print(f"  {name}: {url_source.url[:60]}...")

    manifest_hash = compute_manifest_hash(manifest_path, manifests_dir)
    lock_data = {
        "packages": resolved_packages,
        "target_glibc": raw.target_glibc,
        "toolchain": raw.toolchain,
        "manifest_hash": manifest_hash,
    }

    lock_path = manifests_dir / f"{variant}.lock"
    lock_path.write_text(json.dumps(lock_data, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {lock_path}\n")


def _validate_lock(variant: str, manifests_dir: Path) -> None:
    """Validate that the lock file exists and matches the manifest hash."""
    lock_path = manifests_dir / f"{variant}.lock"
    manifest_path = manifests_dir / f"{variant}.jsonc"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    if not lock_path.exists():
        raise FileNotFoundError(
            f"Lock file not found: {lock_path}. Run 'build.py lock' to generate."
        )

    lockfile = _lockfile_adapter.validate_json(lock_path.read_text())
    current_hash = compute_manifest_hash(manifest_path, manifests_dir)
    if lockfile.manifest_hash != current_hash:
        raise RuntimeError(
            f"Lock file hash mismatch for {variant!r}: manifest changed since lock was "
            f"generated. Run 'build.py lock' to regenerate."
        )


def load_resolved_manifest(
    variant: str,
    manifests_dir: Path | None = None,
) -> ResolvedManifest:
    """Load a resolved manifest from lock file."""
    if manifests_dir is None:
        manifests_dir = PROJECT_ROOT / "manifests"

    _validate_lock(variant, manifests_dir)

    lock_path = manifests_dir / f"{variant}.lock"
    lockfile = _lockfile_adapter.validate_json(lock_path.read_text())
    return ResolvedManifest(
        variant=variant,
        packages=lockfile.packages,
        target_glibc=lockfile.target_glibc,
        toolchain=lockfile.toolchain,
    )
