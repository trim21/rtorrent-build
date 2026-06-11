from __future__ import annotations

from abc import abstractmethod

from ..manifest import LibInfo
from ..run import Commander
from ..toolchain import Builder, ResolvedSource, Toolchain


class MesonBuilder(Builder):
    def __init__(
        self, toolchain: Toolchain, lib: LibInfo, source: ResolvedSource, commander: Commander
    ) -> None:
        self.tc = toolchain
        self.lib = lib
        self.name = source.name
        self.version = source.version
        self.src_dir = source.src_dir
        self.commander = commander

    @abstractmethod
    def meson_args(self, prefix: str) -> list[str]: ...

    @property
    def cache_key_extra(self) -> list[str]:
        return self.meson_args("$PREFIX")

    def build(self) -> None:
        print(f"Building {self.name} {self.version}")
        build_dir = self.src_dir / "build"
        prefix = str(self.tc.install_prefix)
        cmd = self.commander

        cmd.run(
            [
                self.tc.meson_bin,
                "setup",
                str(build_dir),
                "--prefix",
                prefix,
                *self.tc.meson_native_file_args,
                *self.meson_args(prefix),
                str(self.src_dir),
            ],
            env=self.tc.meson_env,
        )
        cmd.run([self.tc.meson_bin, "compile", "-C", str(build_dir), *cmd.nproc_args()])
        cmd.run([self.tc.meson_bin, "install", "-C", str(build_dir)])
        print(f"Built {self.name} {self.version}")
