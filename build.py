"""Entry point script for building static rtorrent binaries.

Usage:
    python build.py rtorrent-0.9.8
    python build.py rtorrent-0.9.8 rtorrent-0.16.11 rtorrent-master
    python build.py                         # builds all variants
    python build.py --libc musl --arch amd/v2 rtorrent-master
"""

from rtorrent_builder.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
