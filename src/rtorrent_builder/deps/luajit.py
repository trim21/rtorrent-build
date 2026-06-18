from __future__ import annotations

from ..manifest import LibInfo
from ..run import Commander
from ..toolchain import ResolvedSource, Toolchain
from ._make import MakeBuilder


class LuaJITBuilder(MakeBuilder):
    default_deps: list[str] = []

    def __init__(
        self, toolchain: Toolchain, lib: LibInfo, source: ResolvedSource, commander: Commander
    ) -> None:
        super().__init__(toolchain, lib, source, commander)

    def make_args(self) -> list[str]:
        return [
            f"PREFIX={self.tc.install_prefix}",
            "BUILDMODE=static",
            f"CC={' '.join(self.tc.zig_cc)}",
            f"HOST_CC={self.tc.zig_bin} cc -fno-sanitize=undefined -O2",
            "XCFLAGS=-DLUAJIT_NO_UNWIND",
        ]

    def install_args(self) -> list[str]:
        return ["install", f"PREFIX={self.tc.install_prefix}"]
