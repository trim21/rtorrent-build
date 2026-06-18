"""Boost builder using cmake (requires -cmake release variant)."""

from __future__ import annotations

from ._cmake import CMakeBuilder


class BoostBuilder(CMakeBuilder):
    def cmake_args(self) -> list[str]:
        return [
            "-DBUILD_SHARED_LIBS=OFF",
            "-DBUILD_TESTING=OFF",
        ]
