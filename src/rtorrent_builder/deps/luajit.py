from __future__ import annotations

from ._make import MakeBuilder


class LuaJITBuilder(MakeBuilder):
    default_deps: list[str] = []

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
