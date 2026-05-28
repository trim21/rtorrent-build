"""Entry point script for building static rtorrent binaries.

Usage:
    python build.py build rtorrent-0.9.8
    python build.py build rtorrent-master --libc musl --arch amd/v2
    python build.py lock
    python build.py lock rtorrent-master
"""

from rtorrent_builder.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
