"""qbittorrent-nox builder (CMake, headless)."""

from __future__ import annotations

from ._cmake import CMakeBuilder


class QbittorrentBuilder(CMakeBuilder):
    def cmake_args(self) -> list[str]:
        return [
            "-DCMAKE_CXX_STANDARD=20",
            "-DGUI=OFF",
            "-DWEBUI=ON",
        ]
