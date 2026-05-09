"""libtorrent-rasterbar builder (arvidn/libtorrent, used by qbittorrent)."""

from __future__ import annotations

from ._cmake import CMakeBuilder


class LibtorrentRasterbarBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        return [
            "-DCMAKE_CXX_STANDARD=17",
            "-DBUILD_SHARED_LIBS=OFF",
            "-Ddeprecated-functions=OFF",
        ]
