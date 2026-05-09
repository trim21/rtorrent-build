"""qbittorrent-nox builder (CMake, headless)."""

from __future__ import annotations

from ._cmake import CMakeBuilder


class QbittorrentBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        return [
            "-DCMAKE_CXX_STANDARD=17",
            "-DGUI=OFF",
            "-DQT6=ON",
            "-DWebUI=ON",
            "-DTESTING=OFF",
        ]
