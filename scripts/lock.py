"""Generate per-manifest lock files: resolves git sources to URL-only manifests."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import json5

from rtorrent_builder.manifest import (
    GitSource,
    LibInfo,
    Source,
    URLSource,
    _raw_manifest_adapter,
    _resolve_extends,
    compute_manifest_hash,
)
from rtorrent_builder.version_range import resolve_best

_MANIFESTS_DIR = Path("manifests").resolve()


def _gh_repo_from_url(url: str) -> str | None:
    """Extract 'owner/repo' from a GitHub URL."""
    m = re.match(r"https?://github\.com/([^/]+/[^/]+?)(?:\.git)?(?:/|$)", url)
    return m.group(1) if m else None


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


def _extract_version(tag: str) -> str | None:
    """Extract version number from a tag like 'v1.2.3' or 'release-5.2.1'."""
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", tag)
    return m.group(1) if m else None


def _resolve_ref(git_url: str, ref: str) -> str:
    result = subprocess.run(
        ["git", "ls-remote", git_url, ref],
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        sha, name = line.split()
        if name == ref or name == f"refs/heads/{ref}" or name == f"refs/tags/{ref}":
            return sha
    raise ValueError(f"Ref {ref} not found in {git_url}")


def _resolve_git_source(git: GitSource) -> tuple[str, str]:
    """Resolve a GitSource to (url, version)."""
    owner_repo = _gh_repo_from_url(git.repo)
    if not owner_repo:
        raise ValueError(f"Cannot parse GitHub repo from URL: {git.repo}")

    if git.tag_range:
        # Resolve tag_range to best matching tag
        tags = _gh_tags(owner_repo)
        versions = [(t, _extract_version(t)) for t in tags]
        version_strings = [v for _, v in versions if v]
        if not version_strings:
            raise ValueError(f"No version tags found for {owner_repo}")
        best = resolve_best(version_strings, git.tag_range)
        tag = next(t for t, v in versions if v == best)
        url = f"https://github.com/{owner_repo}/archive/refs/tags/{tag}.tar.gz"
        return url, best
    else:
        # Resolve ref to SHA, use archive URL
        sha = _resolve_ref(git.repo, git.ref)
        url = f"https://github.com/{owner_repo}/archive/{sha}.tar.gz"
        return url, sha[:12]


def _resolve_source(pkg_name: str, lib: LibInfo) -> tuple[Source, str]:
    """Resolve a LibInfo's source to (URL-only source, version)."""
    if lib.source.url is not None:
        return lib.source, lib.version
    if lib.source.git is not None:
        url, version = _resolve_git_source(lib.source.git)
        return Source(url=URLSource(url=url)), version
    raise ValueError(f"Package {pkg_name!r} has no source")


def resolve_manifest(variant: str, manifests_dir: Path | None = None) -> None:
    """Resolve a manifest to a URL-only lock file."""
    if manifests_dir is None:
        manifests_dir = _MANIFESTS_DIR

    manifest_path = manifests_dir / f"{variant}.jsonc"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    print(f"Resolving {variant}...")
    raw = _raw_manifest_adapter.validate_python(json5.loads(manifest_path.read_text()))
    raw = _resolve_extends(raw, manifests_dir)

    resolved_packages: dict[str, dict] = {}
    for name, pkg in raw.packages.items():
        source, version = _resolve_source(name, pkg)
        entry: dict = {"source": {"url": {"url": source.url.url}}}
        if version:
            entry["version"] = version
        if pkg.cxx_std:
            entry["cxx_std"] = pkg.cxx_std
        resolved_packages[name] = entry
        print(f"  {name}: {source.url.url[:60]}...")

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


def main() -> None:
    for manifest_path in sorted(_MANIFESTS_DIR.glob("*.jsonc")):
        if manifest_path.stem == "common":
            continue
        resolve_manifest(manifest_path.stem)


if __name__ == "__main__":
    main()
