"""Generate PR body summarizing lock file updates.

Compares HEAD (old) lock files vs working tree (new) lock files. URL-sourced
packages only expose a version and an integrity hash, so they are reported as a
plain version table without a changelog. Git-sourced packages additionally get
an upstream commit log from the GitHub compare API.

Usage:
    python scripts/pr-body.py --output-file /tmp/pr-body.md

Output: markdown text written to --output-file (stdout if omitted).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import httpx
from pydantic import ValidationError

from rtorrent_builder.manifest import (
    GitSource,
    LockFile,
    ResolvedPackage,
    _lockfile_adapter,
)


@dataclass(frozen=True, kw_only=True)
class ShaChange:
    package: str
    repo: str  # e.g. "rakshasa/rtorrent"
    old_sha: str
    new_sha: str
    variants: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, kw_only=True)
class VersionBump:
    package: str
    old_version: str
    new_version: str
    new_url: str
    variants: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, kw_only=True)
class SourceChange:
    """A package whose source moved while its version stayed the same."""

    package: str
    version: str
    old_src: ResolvedPackage
    new_src: ResolvedPackage
    variants: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, kw_only=True)
class PresenceChange:
    package: str
    version: str
    variants: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, kw_only=True)
class Commit:
    sha: str
    subject: str


@dataclass(frozen=True, kw_only=True)
class Changes:
    bumps: dict[str, VersionBump] = field(default_factory=dict)
    sources: dict[str, SourceChange] = field(default_factory=dict)
    shas: dict[str, ShaChange] = field(default_factory=dict)
    added: dict[str, PresenceChange] = field(default_factory=dict)
    removed: dict[str, PresenceChange] = field(default_factory=dict)
    lock_count: int = 0

    @property
    def empty(self) -> bool:
        return not (self.bumps or self.sources or self.shas or self.added or self.removed)


def _git_show(path: str) -> str:
    """Read file content from HEAD."""
    result = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"git show HEAD:{path} failed: {result.stderr}")
    return result.stdout


def _load_lock(text: str, source: str) -> LockFile | None:
    """Parse a lock file, or None (with a warning) if it predates the current schema."""
    try:
        return _lockfile_adapter.validate_json(text)
    except ValidationError as e:
        print(f"WARNING: cannot parse {source}: {e}", file=sys.stderr)
        return None


def _repo_from_url(url: str) -> str:
    """Extract 'owner/repo' from a git URL."""
    url = url.removesuffix(".git")
    parts = url.rstrip("/").split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return url


def _sha_of(pkg: ResolvedPackage) -> str:
    return pkg.src.sha if isinstance(pkg.src, GitSource) else ""


def _url_of(pkg: ResolvedPackage) -> str:
    return pkg.src.url if pkg.src is not None else ""


def _record[Entry: (ShaChange, VersionBump, SourceChange, PresenceChange)](
    bucket: dict[str, Entry], key: str, entry: Entry, variant: str
) -> None:
    """Store *entry* under *key*, stamping it with *variant*.

    The records are frozen, so a variant already recorded under the same key is
    merged by rebuilding that entry instead of mutating it in place.
    """
    existing = bucket.get(key)
    if existing is None:
        bucket[key] = replace(entry, variants=frozenset({variant}))
    else:
        bucket[key] = replace(existing, variants=existing.variants | {variant})


def _collect_lock(variant: str, old: LockFile, new: LockFile, out: Changes) -> None:
    """Classify each package's old/new lock entries into *out*."""
    for name in sorted(set(old.packages) | set(new.packages)):
        old_pkg = old.packages.get(name)
        new_pkg = new.packages.get(name)

        if old_pkg is None and new_pkg is not None:
            _record(out.added, name, PresenceChange(package=name, version=new_pkg.version), variant)
            continue
        if new_pkg is None and old_pkg is not None:
            _record(
                out.removed, name, PresenceChange(package=name, version=old_pkg.version), variant
            )
            continue
        if old_pkg is None or new_pkg is None:
            continue

        old_sha, new_sha = _sha_of(old_pkg), _sha_of(new_pkg)
        if old_sha and new_sha and old_sha != new_sha:
            # A git-sourced bump carries its own commit log, which says more
            # than a version column would.
            _record(
                out.shas,
                f"{name}|{old_sha}|{new_sha}",
                ShaChange(
                    package=name,
                    repo=_repo_from_url(_url_of(new_pkg)),
                    old_sha=old_sha,
                    new_sha=new_sha,
                ),
                variant,
            )
            continue

        if old_pkg.version != new_pkg.version:
            _record(
                out.bumps,
                f"{name}|{old_pkg.version}|{new_pkg.version}",
                VersionBump(
                    package=name,
                    old_version=old_pkg.version,
                    new_version=new_pkg.version,
                    new_url=_url_of(new_pkg),
                ),
                variant,
            )
        elif old_pkg.src != new_pkg.src:
            _record(
                out.sources,
                f"{name}|{new_pkg.version}|{old_pkg.src!r}|{new_pkg.src!r}",
                SourceChange(
                    package=name,
                    version=new_pkg.version,
                    old_src=old_pkg,
                    new_src=new_pkg,
                ),
                variant,
            )


def _collect_changes(changed_locks: list[str]) -> Changes:
    """Compare old (HEAD) and new (working tree) lock files."""
    out = Changes(lock_count=len(changed_locks))
    for lock_rel_path in changed_locks:
        lock_path = Path(lock_rel_path)
        variant = lock_path.stem
        if not lock_path.exists():
            continue  # lock file removed; the file diff already shows that
        new_lock = _load_lock(lock_path.read_text(), str(lock_path))
        if new_lock is None:
            continue
        try:
            old_text = _git_show(lock_rel_path)
        except RuntimeError:
            continue  # new lock file, nothing to compare against yet
        old_lock = _load_lock(old_text, f"HEAD:{lock_rel_path}")
        if old_lock is not None:
            _collect_lock(variant, old_lock, new_lock, out)
    return out


def _variants_cell(variants: frozenset[str]) -> str:
    return ", ".join(f"`{v}`" for v in sorted(variants))


def _source_cell(pkg: ResolvedPackage) -> str:
    src = pkg.src
    if src is None:
        return "—"
    bits: list[str] = [f"[url]({src.url})"]
    if isinstance(src, GitSource):
        bits.append(f"`{src.ref or src.sha[:12]}`")
    else:
        bits.append(f"`{src.integrity[:18]}…`")
    return " ".join(bits)


def _fetch_commits(repo: str, old_sha: str, new_sha: str, token: str | None) -> list[Commit]:
    """Fetch commits between old_sha and new_sha via GitHub compare API."""
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{repo}/compare/{old_sha}...{new_sha}"
    resp = httpx.get(url, headers=headers, follow_redirects=True)
    resp.raise_for_status()
    raw_commits: list[dict] = resp.json().get("commits", [])
    return [
        Commit(sha=str(c["sha"]), subject=str(c["commit"]["message"].split("\n")[0]))
        for c in raw_commits
    ]


def _format_summary(changes: Changes) -> str:
    counts = [
        ("version bumps", len(changes.bumps)),
        ("git-sourced bumps", len(changes.shas)),
        ("source changes", len(changes.sources)),
        ("packages added", len(changes.added)),
        ("packages removed", len(changes.removed)),
    ]
    parts = [f"{count} {label}" for label, count in counts if count]
    moved = ", ".join(parts) if parts else "no package changes"
    return f"_{changes.lock_count} lock files changed · {moved}._\n"


def _format_body(changes: Changes, token: str | None) -> str:
    """Generate markdown PR body from collected changes."""
    if changes.empty:
        if not changes.lock_count:
            return "No lock files changed."
        return (
            f"{_format_summary(changes)}\n"
            "No package source changes. Only lock metadata (manifest hash, "
            "target glibc, toolchain) moved."
        )

    lines: list[str] = [_format_summary(changes)]

    if changes.bumps:
        lines.append("## Version updates\n")
        lines.append("| package | old | new | manifests |")
        lines.append("| --- | --- | --- | --- |")
        for bump in sorted(changes.bumps.values(), key=lambda b: (b.package, b.new_version)):
            lines.append(
                f"| {bump.package} | {bump.old_version} | "
                f"[{bump.new_version}]({bump.new_url}) | {_variants_cell(bump.variants)} |"
            )
        lines.append("")

    if changes.sources:
        lines.append("## Source changes (same version)\n")
        lines.append("| package | version | old source | new source | manifests |")
        lines.append("| --- | --- | --- | --- | --- |")
        for change in sorted(changes.sources.values(), key=lambda c: c.package):
            lines.append(
                f"| {change.package} | {change.version} | "
                f"{_source_cell(change.old_src)} | {_source_cell(change.new_src)} | "
                f"{_variants_cell(change.variants)} |"
            )
        lines.append("")

    for label, bucket in (
        ("Packages added", changes.added),
        ("Packages removed", changes.removed),
    ):
        if not bucket:
            continue
        lines.append(f"## {label}\n")
        for item in sorted(bucket.values(), key=lambda p: p.package):
            lines.append(f"- `{item.package}` {item.version} — {_variants_cell(item.variants)}")
        lines.append("")

    if changes.shas:
        lines.append("## Git-sourced updates\n")
        commit_cache: dict[tuple[str, str, str], list[Commit]] = {}
        for change in sorted(changes.shas.values(), key=lambda c: c.package):
            cache_key = (change.repo, change.old_sha, change.new_sha)
            if cache_key not in commit_cache:
                commit_cache[cache_key] = _fetch_commits(
                    change.repo, change.old_sha, change.new_sha, token
                )
            commits = commit_cache[cache_key]
            compare_url = (
                f"https://github.com/{change.repo}/compare/"
                f"{change.old_sha[:12]}...{change.new_sha[:12]}"
            )
            count = len(commits)

            lines.append(
                f"### {change.package} ([`{change.repo}`](https://github.com/{change.repo}))\n"
            )
            lines.append(
                f"[`{change.old_sha[:7]}...{change.new_sha[:7]}`]({compare_url})"
                f" ({count} commit{'s' if count != 1 else ''})"
                f" — {_variants_cell(change.variants)}\n"
            )
            for commit in commits:
                subject = commit.subject
                if len(subject) > 120:
                    subject = subject[:117] + "..."
                # Escape @ so GitHub does not turn usernames in commit messages
                # into mentions on the PR.
                subject = subject.replace("@", "@<!-- -->")
                commit_url = f"https://github.com/{change.repo}/commit/{commit.sha}"
                lines.append(f"- [`{commit.sha[:7]}`]({commit_url}) {subject}")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PR body from lock file changes")
    parser.add_argument("--output-file", help="Write output to file instead of stdout")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")

    # Find changed lock files by comparing HEAD with working tree
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "manifests/*.lock"],
        capture_output=True,
        text=True,
        cwd=os.getcwd(),
    )
    changed_files = [f for f in result.stdout.strip().split("\n") if f]

    body = _format_body(_collect_changes(changed_files), token)

    if args.output_file:
        Path(args.output_file).write_text(body)
    else:
        print(body)


if __name__ == "__main__":
    main()
