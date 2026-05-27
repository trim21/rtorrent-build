"""Create a manifest for the latest rtorrent release tag if one doesn't exist."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

_MANIFESTS_DIR = Path("manifests").resolve()
_REPO = "rakshasa/rtorrent"
_GLIBC_TARGET = "2.28"


def _existing_variants() -> set[str]:
    return {p.stem for p in _MANIFESTS_DIR.glob("rtorrent-*.jsonc")}


def _fetch_latest_release() -> dict[str, str]:
    resp = httpx.get(
        f"https://api.github.com/repos/{_REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json"},
        follow_redirects=True,
    )
    resp.raise_for_status()
    data = resp.json()
    tag: str = data["tag_name"]
    version = tag.lstrip("v")
    return {"tag": tag, "version": version}


def _manifest_content(version: str) -> str:
    obj = {
        "extends": "common.jsonc",
        "target_glibc": _GLIBC_TARGET,
        "packages": {
            "rtorrent": {
                "source": {
                    "url": f"https://github.com/{_REPO}/releases/download/v{version}/rtorrent-{version}.tar.gz",
                },
                "version": version,
            },
            "rtorrent-libtorrent": {
                "source": {
                    "url": f"https://github.com/{_REPO}/releases/download/v{version}/libtorrent-{version}.tar.gz",
                },
                "version": version,
            },
        },
    }
    return json.dumps(obj, indent=2) + "\n"


def main() -> None:
    release = _fetch_latest_release()
    version = release["version"]
    variant = f"rtorrent-{version}"

    if variant in _existing_variants():
        print(f"Manifest for {variant} already exists, nothing to do")
        return

    path = _MANIFESTS_DIR / f"{variant}.jsonc"
    path.write_text(_manifest_content(version))
    print(f"Created {path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
