"""Generate PR body with upstream commit logs for lock file updates.

Compares HEAD (old) lock files vs working tree (new) lock files, fetches
commit logs from GitHub API for each git-sourced package whose SHA changed.

Usage:
    python scripts/pr-body.py --output-file /tmp/pr-body.md

Output: markdown text written to --output-file (stdout if omitted).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True)
class ShaChange:
    package: str
    repo: str  # e.g. "rakshasa/rtorrent"
    old_sha: str
    new_sha: str


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


def _extract_sha_from_lock(lock_data: dict, package: str) -> tuple[str, str] | None:
    """Return (sha, repo_url) for a git-sourced package in a lock file."""
    pkg = lock_data.get("packages", {}).get(package)
    if not pkg:
        return None
    src = pkg.get("src")
    if not src:
        return None
    sha = src.get("sha")
    url = src.get("url", "")
    if not sha:
        return None
    return sha, url


def _repo_from_url(url: str) -> str:
    """Extract 'owner/repo' from a git URL."""
    url = url.removesuffix(".git")
    parts = url.rstrip("/").split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return url


def _collect_changes(manifest_path: Path) -> list[ShaChange]:
    """Compare old (HEAD) and new (working tree) lock files for a manifest."""
    lock_path = manifest_path.with_suffix(".lock")
    # git diff paths are relative to repo root, use as-is for git show
    rel_path = str(lock_path)

    try:
        old_text = _git_show(rel_path)
    except RuntimeError:
        return []  # new lock file, no HEAD version

    new_text = lock_path.read_text()

    old_data = json.loads(old_text)
    new_data = json.loads(new_text)

    changes: list[ShaChange] = []
    for pkg_name in new_data.get("packages", {}):
        old_info = _extract_sha_from_lock(old_data, pkg_name)
        new_info = _extract_sha_from_lock(new_data, pkg_name)
        if not old_info or not new_info:
            continue
        old_sha, _ = old_info
        new_sha, url = new_info
        if old_sha != new_sha:
            repo = _repo_from_url(url)
            changes.append(ShaChange(package=pkg_name, repo=repo, old_sha=old_sha, new_sha=new_sha))

    return changes


def _fetch_commits(repo: str, old_sha: str, new_sha: str, token: str | None) -> list[dict]:
    """Fetch commits between old_sha and new_sha via GitHub compare API."""
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{repo}/compare/{old_sha}...{new_sha}"
    resp = httpx.get(url, headers=headers, follow_redirects=True)
    resp.raise_for_status()
    data = resp.json()
    return data.get("commits", [])


def _format_body(
    changes: list[ShaChange],
    token: str | None,
    *,
    manifest_name: str | None = None,
) -> str:
    """Generate markdown PR body from collected changes."""
    if not changes:
        return "No git-sourced package changes detected."

    # Deduplicate by (repo, old_sha, new_sha)
    seen: set[tuple[str, str, str]] = set()
    unique: list[ShaChange] = []
    for c in changes:
        key = (c.repo, c.old_sha, c.new_sha)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    lines: list[str] = []
    if manifest_name:
        lines.append(f"## Changes for `{manifest_name}`\n")

    for change in unique:
        commits = _fetch_commits(change.repo, change.old_sha, change.new_sha, token)
        count = len(commits)

        compare_url = (
            f"https://github.com/{change.repo}/compare/"
            f"{change.old_sha[:12]}...{change.new_sha[:12]}"
        )

        lines.append(
            f"### {change.package} ([`{change.repo}`](https://github.com/{change.repo}))\n"
        )
        lines.append(
            f"[`{change.old_sha[:7]}...{change.new_sha[:7]}`]({compare_url})"
            f" ({count} commit{'s' if count != 1 else ''})\n"
        )

        for c in commits:
            sha: str = c["sha"]
            msg: str = c["commit"]["message"].split("\n")[0]
            # Escape @ to prevent GitHub from treating usernames in commit
            # messages as mentions in the PR body.
            msg = msg.replace("@", "@<!-- -->")
            if len(msg) > 120:
                msg = msg[:117] + "..."
            commit_url = f"https://github.com/{change.repo}/commit/{sha}"
            lines.append(f"- [`{sha[:7]}`]({commit_url}) {msg}")

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

    if not changed_files:
        body = "No lock files changed."
    else:
        all_changes: list[ShaChange] = []
        for lock_rel_path in changed_files:
            lock_path = Path(lock_rel_path)
            manifest_path = lock_path.with_suffix(".jsonc")
            if not manifest_path.exists():
                continue
            changes = _collect_changes(manifest_path)
            if changes:
                all_changes.extend(changes)
        body = _format_body(all_changes, token)

    if args.output_file:
        Path(args.output_file).write_text(body)
    else:
        print(body)


if __name__ == "__main__":
    main()
