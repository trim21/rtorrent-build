from __future__ import annotations

from typing import ClassVar

from ._cmake import CMakeBuilder


class LibdeflateBuilder(CMakeBuilder):
    default_deps: ClassVar[list[str]] = []

    def cmake_args(self) -> list[str]:
        return [
            "-DLIBDEFLATE_COMPRESSION_SUPPORT=ON",
            "-DLIBDEFLATE_DECOMPRESSION_SUPPORT=ON",
            "-DLIBDEFLATE_ZLIB_SUPPORT=ON",
            "-DLIBDEFLATE_GZIP_SUPPORT=ON",
            "-DLIBDEFLATE_BUILD_GZIP=OFF",
            "-DLIBDEFLATE_BUILD_SHARED_LIB=OFF",
            "-DLIBDEFLATE_BUILD_TESTS=OFF",
        ]
