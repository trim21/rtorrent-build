"""qbittorrent-nox builder (CMake, headless)."""

from __future__ import annotations

from ._cmake import CMakeBuilder


class QbittorrentBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        args = [
            "-DCMAKE_CXX_STANDARD=17",
            "-DGUI=OFF",
            "-DQT6=ON",
            "-DWebUI=ON",
            "-DTESTING=OFF",
        ]
        if self.tc.shared_deps:
            args.append(
                f"-DCMAKE_EXE_LINKER_FLAGS=-Wl,--no-allow-shlib-undefined{self.tc.final_ldflags}"
            )
        return args
