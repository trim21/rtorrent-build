from __future__ import annotations

from ..manifest import LibInfo
from ..toolchain import ResolvedSource, Toolchain
from ._make import MakeBuilder


class LuaJITBuilder(MakeBuilder):
    def __init__(self, toolchain: Toolchain, lib: LibInfo, source: ResolvedSource) -> None:
        super().__init__(toolchain, lib, source)
        self._build_env: dict[str, str] | None = None

    @property
    def build_env(self) -> dict[str, str] | None:
        return self._build_env

    def make_args(self) -> list[str]:
        return [
            f"PREFIX={self.tc.install_prefix}",
            "BUILDMODE=static",
            f"CC={' '.join(self.tc.zig_cc)}",
            "XCFLAGS=-DLUAJIT_NO_UNWIND -g -flto",
            "LDFLAGS=-flto",
        ]

    def install_args(self) -> list[str]:
        return ["install", f"PREFIX={self.tc.install_prefix}"]
