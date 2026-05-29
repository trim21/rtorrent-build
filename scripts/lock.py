"""Generate per-manifest lock files: resolves git sources to URL-only manifests."""

from __future__ import annotations

from pathlib import Path

from rtorrent_builder.lock import resolve_manifest

_MANIFESTS_DIR = Path("manifests").resolve()


def main() -> None:
    for manifest_path in sorted(_MANIFESTS_DIR.glob("*.jsonc")):
        resolve_manifest(manifest_path)


if __name__ == "__main__":
    main()
