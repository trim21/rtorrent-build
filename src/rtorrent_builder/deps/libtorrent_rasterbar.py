"""libtorrent-rasterbar builder (arvidn/libtorrent, used by qbittorrent)."""

from __future__ import annotations

from ..utils import conditional_args, replace_in_file
from ._cmake import CMakeBuilder


class LibtorrentRasterbarBuilder(CMakeBuilder):
    default_deps: list[str] = ["boost", "openssl", "curl"]

    def cmake_args(self) -> list[str]:
        cxx_std = self.lib.cxx_std.removeprefix("c++") if self.lib.cxx_std else None
        return conditional_args({
            "-DBUILD_SHARED_LIBS=OFF": True,
            "-Ddeprecated-functions=OFF": True,
            # libdatachannel examples/* and test/* are git submodules not included
            # in the release tarball; disable them all to avoid CMake errors.
            "-DNO_EXAMPLES=ON": True,
            "-DNO_TESTS=ON": True,
            "-DNO_BENCHMARK=ON": True,
            f"-DCMAKE_CXX_STANDARD={cxx_std}": cxx_std is not None,
        })

    def cache_key_extra(self) -> list[str]:
        return super().cache_key_extra() + [
            "patch:CMakeLists.txt:-Weverything+narrowing",
        ]

    def generate(self) -> None:
        replace_in_file(
            self.src_dir / "CMakeLists.txt",
            "\t\t-Weverything\n",
            "\t\t-Weverything\n\t\t-Wno-c++11-narrowing-const-reference\n",
        )
        super().generate()
