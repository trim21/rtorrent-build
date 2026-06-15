from __future__ import annotations

from ._cmake import CMakeBuilder


class CaresBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        if self.tc.shared_deps:
            return [
                "-DCARES_STATIC=OFF",
                "-DCARES_SHARED=ON",
                "-DCARES_BUILD_TOOLS=OFF",
            ]
        return [
            "-DCARES_STATIC=ON",
            "-DCARES_SHARED=OFF",
            "-DCARES_BUILD_TOOLS=OFF",
        ]
