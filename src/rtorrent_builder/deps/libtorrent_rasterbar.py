"""libtorrent-rasterbar builder (arvidn/libtorrent, used by qbittorrent)."""

from __future__ import annotations

from ..utils import replace_in_file
from ._cmake import CMakeBuilder


class LibtorrentRasterbarBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        args = [
            "-Ddeprecated-functions=OFF",
        ]
        if not self.tc.shared_deps:
            args.append("-DBUILD_SHARED_LIBS=OFF")
        if self.lib.cxx_std:
            args.append(f"-DCMAKE_CXX_STANDARD={self.lib.cxx_std.removeprefix('c++')}")
        return args

    def build(self) -> None:
        replace_in_file(
            self.src_dir / "CMakeLists.txt",
            "\t\t-Weverything\n",
            "\t\t-Weverything\n\t\t-Wno-c++11-narrowing-const-reference\n",
        )
        super().build()
