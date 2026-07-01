"""Lock file generation: resolves git sources to URL-only manifests."""

from __future__ import annotations

import re
import subprocess
from functools import cache
from pathlib import Path

from . import PROJECT_ROOT
from .builder import compute_deps
from .download import compute_sha256, download_file
from .manifest import (
    ChecksumSource,
    GenericRefSource,
    GitHubPrSource,
    GitHubRefSource,
    GitHubReleaseSource,
    GitHubTagSource,
    GitSource,
    LibInfo,
    LockFile,
    PackageSource,
    ResolvedManifest,
    ResolvedPackage,
    URLSource,
    _load_jsonc_text,
    _lockfile_adapter,
    _raw_manifest_adapter,
    _resolve_extends,
    compute_manifest_hash,
    reachable_packages,
)
from .version_range import resolve_best

_VERSION_PATTERNS: dict[str, str] = {
    "boostorg/boost": r"^boost-(\d+)\.(\d+)\.(\d+)(?:-\d+)?$",
    "curl/curl": r"^curl-(\d+)_(\d+)_(\d+)$",
    "openssl/openssl": r"^openssl-(\d+)\.(\d+)\.(\d+)$",
    "qbittorrent/qBittorrent": r"^release-(\d+)\.(\d+)\.(\d+)$",
}


@cache
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


@cache
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


@cache
def _resolve_generic_ref(url: str, ref: str) -> str:
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
    raise ValueError(f"Ref {ref} not found in {url}")


def _resolve_pr(github: str, pr: int) -> tuple[GitSource, str]:
    """Resolve a GitHub PR to its merge commit (refs/pull/{pr}/merge).

    Falls back to the PR head commit if the merge ref is not available
    (e.g. PR has conflicts or is not mergeable).
    """
    url = f"https://github.com/{github}.git"
    merge_ref = f"refs/pull/{pr}/merge"
    head_ref = f"refs/pull/{pr}/head"
    result = subprocess.run(
        ["git", "ls-remote", url, merge_ref, head_ref],
        capture_output=True,
        text=True,
        check=True,
    )
    merge_sha: str | None = None
    head_sha: str | None = None
    for line in result.stdout.splitlines():
        sha, name = line.split()
        if name == merge_ref:
            merge_sha = sha
        elif name == head_ref:
            head_sha = sha

    if merge_sha:
        print(f"  PR #{pr} merge commit: {merge_sha[:12]}")
        return GitSource(url=url, sha=merge_sha), merge_sha[:12]
    if head_sha:
        print(f"  WARNING: PR #{pr} has no merge commit (conflicts?), using head: {head_sha[:12]}")
        return GitSource(url=url, sha=head_sha), head_sha[:12]
    raise ValueError(f"PR #{pr} not found in {github}")


def _resolve_github_source(source: PackageSource) -> tuple[str, str] | tuple[GitSource, str]:
    """Resolve a GitHub source to (url, version) or (GitSource, version)."""
    if isinstance(source, GitHubRefSource):
        sha = _resolve_ref(source.github, source.ref)
        return GitSource(
            url=f"https://github.com/{source.github}.git",
            sha=sha,
        ), sha[:12]
    if isinstance(source, GitHubPrSource):
        return _resolve_pr(source.github, source.pr)
    if isinstance(source, (GitHubTagSource, GitHubReleaseSource)):
        tags = _gh_tags(source.github)
        versions = [(t, _extract_version(t, source.github)) for t in tags]
        version_strings = [v for _, v in versions if v]
        if not version_strings:
            raise ValueError(f"No version tags found for {source.github}")
        best = resolve_best(version_strings, source.tag_range)
        matching_tags = [t for t, v in versions if v == best]
        tag = max(matching_tags, key=len)
        if isinstance(source, GitHubReleaseSource):
            asset = source.asset.format(tag=tag, version=best)
            url = f"https://github.com/{source.github}/releases/download/{tag}/{asset}"
        elif isinstance(source, GitHubTagSource) and source.url_template:
            url = source.url_template.format(tag=tag, version=best)
        else:
            url = f"https://github.com/{source.github}/archive/refs/tags/{tag}.tar.gz"
        return url, best
    raise TypeError(f"Unsupported git source type: {type(source)}")


def _resolve_source(pkg_name: str, lib: LibInfo) -> tuple[PackageSource, str]:
    """Resolve a LibInfo's source to (source, version)."""
    if isinstance(lib.source, URLSource):
        return lib.source, lib.version
    if isinstance(lib.source, GenericRefSource):
        sha = _resolve_generic_ref(lib.source.git, lib.source.ref)
        return GitSource(url=lib.source.git, sha=sha), sha[:12]
    if isinstance(
        lib.source, (GitHubRefSource, GitHubPrSource, GitHubTagSource, GitHubReleaseSource)
    ):
        resolved, version = _resolve_github_source(lib.source)
        if isinstance(resolved, GitSource):
            return resolved, version
        return URLSource(url=resolved), version
    raise ValueError(f"Package {pkg_name!r} has no source")


_ASSETS_DIR = PROJECT_ROOT / "assets"


def _download_and_hash(url: str, name: str, version: str, assets_dir: Path) -> str:
    """Download a tarball and return its integrity hash (sha256:<hex>)."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    dest = assets_dir / f"{name}-{version}"
    if not dest.exists():
        download_file(url, dest, desc=f"{name}-{version}")
    digest = compute_sha256(dest)
    return f"sha256:{digest}"


def resolve_manifest(manifest_path: Path) -> None:
    """Resolve a manifest to a URL-only lock file."""
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    variant = manifest_path.stem
    manifests_dir = manifest_path.parent

    print(f"Resolving {variant}...")
    raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
    raw = _resolve_extends(raw, manifests_dir)

    if raw.executable_package:
        all_features, default_deps = compute_deps()
        reachable = reachable_packages(
            raw.packages,
            raw.executable_package,
            all_features=all_features,
            default_deps=default_deps,
        )
    else:
        reachable = set(raw.packages)

    resolved_packages: dict[str, ResolvedPackage] = {}
    for name, pkg in raw.packages.items():
        if name not in reachable:
            continue
        resolved_source, version = _resolve_source(name, pkg)
        if isinstance(resolved_source, GitSource):
            rpkg = ResolvedPackage(
                version=version,
                src=resolved_source,
                cxx_std=pkg.cxx_std,
                requires=pkg.requires,
                features=pkg.features,
            )
        elif isinstance(resolved_source, URLSource):
            integrity = _download_and_hash(resolved_source.url, name, version, _ASSETS_DIR)
            rpkg = ResolvedPackage(
                version=version,
                src=ChecksumSource(url=resolved_source.url, integrity=integrity),
                cxx_std=pkg.cxx_std,
                requires=pkg.requires,
                features=pkg.features,
            )
        else:
            raise TypeError(f"Unexpected source type for {name}: {type(resolved_source)}")
        resolved_packages[name] = rpkg
        src_url = (
            resolved_source.url
            if isinstance(resolved_source, URLSource | GitSource)
            else "<unknown>"
        )
        print(f"  {name}: {src_url[:60]}...")

    manifest_hash = compute_manifest_hash(manifest_path)
    lockfile = LockFile(
        packages=resolved_packages,
        target_glibc=raw.target_glibc or "",
        toolchain=raw.toolchain or "",
        manifest_hash=manifest_hash,
        executable_package=raw.executable_package or "",
    )

    lock_path = manifest_path.with_suffix(".lock")
    lock_path.write_text(
        _lockfile_adapter.dump_json(lockfile, indent=2, exclude_defaults=True).decode() + "\n"
    )
    print(f"Wrote {lock_path}\n")


def _validate_lock(manifest_path: Path) -> None:
    """Validate that the lock file exists and matches the manifest hash."""
    lock_path = manifest_path.with_suffix(".lock")

    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    if not lock_path.exists():
        raise FileNotFoundError(
            f"Lock file not found: {lock_path}. Run 'build.py lock' to generate."
        )

    lockfile = _lockfile_adapter.validate_json(lock_path.read_text())
    current_hash = compute_manifest_hash(manifest_path)
    if lockfile.manifest_hash != current_hash:
        raise RuntimeError(
            f"Lock file hash mismatch for {manifest_path.stem!r}: manifest changed since lock was "
            f"generated. Run 'build.py lock' to regenerate."
        )


def load_resolved_manifest(manifest_path: Path) -> ResolvedManifest:
    """Load a resolved manifest from lock file."""
    manifest_path = Path(manifest_path)
    _validate_lock(manifest_path)

    lock_path = manifest_path.with_suffix(".lock")
    lockfile = _lockfile_adapter.validate_json(lock_path.read_text())
    return ResolvedManifest(
        variant=manifest_path.stem,
        packages=lockfile.packages,
        target_glibc=lockfile.target_glibc,
        toolchain=lockfile.toolchain,
        executable_package=lockfile.executable_package,
    )
