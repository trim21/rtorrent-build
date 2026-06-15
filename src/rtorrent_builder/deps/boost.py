"""Boost builder using cmake (requires -cmake release variant)."""

from __future__ import annotations

from ._cmake import CMakeBuilder


class BoostBuilder(CMakeBuilder):
    def cmake_args(self, prefix: str) -> list[str]:
        flags = ["-DBUILD_TESTING=OFF"]
        if not self.tc.shared_deps:
            flags.append("-DBUILD_SHARED_LIBS=OFF")
        return flags
