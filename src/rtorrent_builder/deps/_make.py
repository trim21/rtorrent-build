from __future__ import annotations

from abc import abstractmethod

from ..manifest import LibInfo
from ..toolchain import Builder, ResolvedSource, Toolchain


class MakeBuilder(Builder):
    def __init__(self, toolchain: Toolchain, lib: LibInfo, source: ResolvedSource) -> None:
        self.tc = toolchain
        self.lib = lib
        self.name = source.name
        self.version = source.version
        self.src_dir = source.src_dir

    @property
    def build_env(self) -> dict[str, str] | None:
        return self.tc.env

    def configure(self) -> None:
        pass

    @abstractmethod
    def make_args(self) -> list[str]: ...

    @abstractmethod
    def install_args(self) -> list[str]: ...

    def build(self) -> None:
        print(f"Building {self.name} {self.version}")
        cmd = self.tc.commander
        self.configure()
        cmd.run(["make", *self.make_args()], cwd=str(self.src_dir), env=self.build_env)
        cmd.run(["make", *self.install_args()], cwd=str(self.src_dir), env=self.build_env)
        print(f"Built {self.name} {self.version}")
