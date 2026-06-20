"""libtorrent-rasterbar builder (arvidn/libtorrent, used by qbittorrent)."""

from __future__ import annotations

from ..utils import replace_in_file
from ._cmake import CMakeBuilder


class LibtorrentRasterbarBuilder(CMakeBuilder):
    default_deps: list[str] = ["boost", "openssl", "curl"]

    def cmake_args(self) -> list[str]:
        args = [
            "-DBUILD_SHARED_LIBS=OFF",
            "-Ddeprecated-functions=OFF",
        ]
        if self.lib.cxx_std:
            args.append(f"-DCMAKE_CXX_STANDARD={self.lib.cxx_std.removeprefix('c++')}")
        return args

    def cache_key_extra(self) -> list[str]:
        return super().cache_key_extra() + [
            "patch:CMakeLists.txt:-Weverything+narrowing",
        ]

    def build(self) -> None:
        replace_in_file(
            self.src_dir / "CMakeLists.txt",
            "\t\t-Weverything\n",
            "\t\t-Weverything\n\t\t-Wno-c++11-narrowing-const-reference\n",
        )
        super().build()
