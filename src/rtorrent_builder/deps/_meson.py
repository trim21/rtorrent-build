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

    def cache_key_extra(self) -> list[str]:
        extra = super().cache_key_extra()
        extra += self.meson_args("$PREFIX")
        return extra

    @property
    def meson_build_dir(self) -> str:
        return str(self.src_dir / "build")

    def generate(self) -> None:
        print(f"Generating {self.name} {self.version}")
        self._apply_patches()
        prefix = str(self.tc.install_prefix)
        cmd = self.commander

        cmd.run(
            [
                self.tc.meson_bin,
                "setup",
                self.meson_build_dir,
                "--prefix",
                prefix,
                *self.tc.meson_native_file_args,
                *self.meson_args(prefix),
                str(self.src_dir),
            ],
            env=self.tc.meson_env,
        )

    def build(self) -> None:
        print(f"Building {self.name} {self.version}")
        self.commander.run(
            [
                self.tc.meson_bin,
                "compile",
                "-C",
                self.meson_build_dir,
                *self.commander.nproc_args(),
            ]
        )

    def install(self) -> None:
        self.commander.run(
            [self.tc.meson_bin, "install", "-C", self.meson_build_dir],
        )
        print(f"Built {self.name} {self.version}")
