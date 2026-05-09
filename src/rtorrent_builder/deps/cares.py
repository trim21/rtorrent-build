from __future__ import annotations

from ._cmake import CMakeBuilder


class CaresBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        return [
            "-DCARES_STATIC=ON",
            "-DCARES_SHARED=OFF",
            "-DCARES_BUILD_TOOLS=OFF",
        ]
