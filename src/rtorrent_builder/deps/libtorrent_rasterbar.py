"""libtorrent-rasterbar builder (arvidn/libtorrent, used by qbittorrent)."""

from __future__ import annotations

from ._cmake import CMakeBuilder


class LibtorrentRasterbarBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        args = [
            "-DBUILD_SHARED_LIBS=OFF",
            "-Ddeprecated-functions=OFF",
        ]
        if self.lib.cxx_std:
            args.append(f"-DCMAKE_CXX_STANDARD={self.lib.cxx_std.removeprefix('c++')}")
        return args
