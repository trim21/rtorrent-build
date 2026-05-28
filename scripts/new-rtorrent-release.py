"""Create or update a manifest for the latest rtorrent release."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import httpx
from packaging.specifiers import SpecifierSet

from rtorrent_builder.manifest import _load_jsonc_text

_MANIFESTS_DIR = Path("manifests").resolve()
_REPO = "rakshasa/rtorrent"
_GIT_URL = f"https://github.com/{_REPO}.git"
_GLIBC_TARGET = "2.28"
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?(.*)")


def _fetch_latest_release() -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = httpx.get(
        f"https://api.github.com/repos/{_REPO}/releases/latest",
        headers=headers,
        follow_redirects=True,
    )
    resp.raise_for_status()
    data = resp.json()
    tag: str = data["tag_name"]
    version = tag.lstrip("v")
    return {"tag": tag, "version": version}


def _read_existing_tag_range(manifest_path: Path) -> str | None:
    if not manifest_path.exists():
        return None
    data: dict = _load_jsonc_text(manifest_path.read_text())  # type: ignore[assignment]
    source = data.get("packages", {}).get("rtorrent", {}).get("source", {})
    return source.get("git", {}).get("tag_range")


def _manifest_content(version_prefix: str) -> str:
    tag_range = f">={version_prefix},<{_next_minor(version_prefix)}"
    obj = {
        "$schema": "../manifest.schema.json",
        "extends": "common.jsonc",
        "target_glibc": _GLIBC_TARGET,
        "packages": {
            "rtorrent": {
                "source": {
                    "git": {
                        "repo": _GIT_URL,
                        "tag_range": tag_range,
                    }
                },
            },
            "rtorrent-libtorrent": {
                "source": {
                    "git": {
                        "repo": "https://github.com/rakshasa/libtorrent.git",
                        "tag_range": tag_range,
                    }
                },
            },
        },
    }
    return json.dumps(obj, indent=2) + "\n"


def _next_minor(version_prefix: str) -> str:
    major, minor = version_prefix.split(".")
    return f"{major}.{int(minor) + 1}"


def main() -> None:
    release = _fetch_latest_release()
    version = release["version"]

    m = _VERSION_RE.match(version)
    if not m:
        print(f"Unexpected version format: {version}")
        sys.exit(1)

    major, minor = m.group(1), m.group(2)
    version_prefix = f"{major}.{minor}"
    manifest_path = _MANIFESTS_DIR / f"rtorrent-{version_prefix}.jsonc"

    existing_range = _read_existing_tag_range(manifest_path)
    if existing_range and version in SpecifierSet(existing_range):
        print(f"Version {version} covered by existing {manifest_path.name} ({existing_range})")
        return

    if manifest_path.exists():
        manifest_path.write_text(_manifest_content(version_prefix))
        print(f"Updated {manifest_path.name} for {version}")
    else:
        manifest_path.write_text(_manifest_content(version_prefix))
        print(f"Created {manifest_path.name} for {version}")


if __name__ == "__main__":
    main()
