from __future__ import annotations

from abc import abstractmethod

from ..manifest import LibInfo
from ..run import Commander
from ..toolchain import Builder, ResolvedSource, Toolchain


class CMakeBuilder(Builder):
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
    def cmake_args(self) -> list[str]: ...

    def cache_key_extra(self) -> list[str]:
        return super().cache_key_extra() + self.cmake_args()

    @property
    def cmake_build_dir(self) -> str:
        return str(self.src_dir / "build")

    def generate(self) -> None:
        print(f"Generating {self.name} {self.version}")
        env = self.tc.cmake_env
        prefix = str(self.tc.install_prefix)
        cmd = self.commander

        build_type = "Debug" if self.tc.debug else "RelWithDebInfo"
        cmd.run(
            [
                self.tc.cmake_bin,
                "-B",
                self.cmake_build_dir,
                *self.tc.cmake_common_args,
                f"-DCMAKE_INSTALL_PREFIX={prefix}",
                f"-DCMAKE_BUILD_TYPE={build_type}",
                "-DBUILD_SHARED_LIBS=OFF",
                "-DBUILD_TESTING=OFF",
                *self.cmake_args(),
                "-S",
                str(self.src_dir),
            ],
            env=env,
        )

    def build(self) -> None:
        print(f"Building {self.name} {self.version}")
        cmd = self.commander
        cmd.run(
            [self.tc.cmake_bin, "--build", self.cmake_build_dir, *cmd.nproc_args()],
            env=self.tc.cmake_env,
        )

    def install(self) -> None:
        self.commander.run(
            [self.tc.cmake_bin, "--install", self.cmake_build_dir],
            env=self.tc.cmake_env,
        )
        print(f"Built {self.name} {self.version}")
