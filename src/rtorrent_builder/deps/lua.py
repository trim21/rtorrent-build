from typing import ClassVar

from ._make import MakeBuilder


class LuaBuilder(MakeBuilder):
    default_deps: ClassVar[list[str]] = []

    def make_args(self) -> list[str]:
        return ["generic", f"CC={' '.join(self.tc.zig_cc)}", *self.commander.nproc_args()]

    def install_args(self) -> list[str]:
        return ["install", f"INSTALL_TOP={self.tc.install_prefix}"]
