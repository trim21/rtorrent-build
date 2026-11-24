from __future__ import annotations

from abc import abstractmethod
from typing import ClassVar

from ..manifest import LibInfo
from ..run import Commander
from ..toolchain import Builder, ResolvedSource, Toolchain


class CMakeBuilder(Builder):
    # zig 0.17's bundled LLVM aborts with "Broken module found" when the LTO
    # link verifies bitcode emitted with -g for some C++ codebases; builders
    # that hit this set no_lto to compile without -flto (linker keeps -flto so
    # dependency bitcode archives still link).
    no_lto: bool = False

    # Qt-based builders that need the Qt host tools (moc/rcc/uic/syncqt) at build
    # time.  Those tools are compiled with the target arch and then executed, so
    # they need a separately built copy when the target arch can be newer than the
    # build machine (see host_tools in Toolchain).
    uses_host_tools: ClassVar[bool] = False

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

    def host_tools_args(self) -> list[str]:
        if not self.uses_host_tools or self.tc.host_tools or self.tc.host_tools_prefix is None:
            return []
        return [f"-DQT_HOST_PATH={self.tc.host_tools_prefix}"]

    def no_lto_args(self) -> list[str]:
        if not self.no_lto:
            return []
        flags = self.tc.cmake_cflags_no_lto
        return [f"-DCMAKE_C_FLAGS={flags}", f"-DCMAKE_CXX_FLAGS={flags}"]

    def cache_key_extra(self) -> list[str]:
        return (
            super().cache_key_extra()
            + self.no_lto_args()
            + self.host_tools_args()
            + self.cmake_args()
        )

    @property
    def cmake_build_dir(self) -> str:
        return str(self.src_dir / self.tc.cmake_build_dirname)

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
                *self.no_lto_args(),
                *self.host_tools_args(),
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
