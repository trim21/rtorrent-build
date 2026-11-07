"""Boost builder using cmake (requires -cmake release variant)."""

from __future__ import annotations

from typing import ClassVar

from ._cmake import CMakeBuilder


class BoostBuilder(CMakeBuilder):
    default_deps: ClassVar[list[str]] = []

    def cmake_args(self) -> list[str]:
        return [
            "-DBUILD_SHARED_LIBS=OFF",
            "-DBUILD_TESTING=OFF",
        ]
