"""Generate per-manifest lock files: resolves git refs to commit SHAs."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rtorrent_builder.manifest import Lock, _collect_lock_entries, compute_manifest_hash, save_lock

_MANIFESTS_DIR = Path("manifests").resolve()


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


def main() -> None:
    for manifest_path in sorted(_MANIFESTS_DIR.glob("*.jsonc")):
        if manifest_path.stem == "common":
            continue

        entries = _collect_lock_entries(manifest_path, _MANIFESTS_DIR)
        manifest_hash = compute_manifest_hash(manifest_path, _MANIFESTS_DIR)

        if not entries:
            continue

        lock = Lock(
            git={key: _resolve_ref(*key.split("#", 1)) for key in sorted(entries)},
            manifest_hash=manifest_hash,
        )

        for key, sha in lock.git.items():
            print(f"  {key} -> {sha}")

        save_lock(lock, _MANIFESTS_DIR, manifest_path.stem)
        print(f"Wrote {len(lock.git)} entries to {_MANIFESTS_DIR / manifest_path.stem}.lock\n")


if __name__ == "__main__":
    main()
