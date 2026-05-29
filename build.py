"""Entry point script for building static rtorrent binaries.

Usage:
    python build.py build manifests/rtorrent-0.9.8.jsonc
    python build.py build manifests/rtorrent-master.jsonc --libc musl --arch amd/v2
    python build.py lock
    python build.py lock manifests/rtorrent-master.jsonc
"""

from rtorrent_builder.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
