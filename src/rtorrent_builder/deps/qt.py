"""Qt 6 (qtbase) builder for headless/static builds."""

from __future__ import annotations

from ..manifest import LibInfo
from ..run import Commander
from ..toolchain import Builder, ResolvedSource, Toolchain


class QtBuilder(Builder):
    def __init__(
        self, toolchain: Toolchain, lib: LibInfo, source: ResolvedSource, commander: Commander
    ) -> None:
        self.tc = toolchain
        self.lib = lib
        self.name = source.name
        self.version = source.version
        self.src_dir = source.src_dir
        self.commander = commander

    @property
    def cache_key_extra(self) -> list[str]:
        return [
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_SHARED_LIBS=OFF",
            "-DFEATURE_shared=OFF",
            "-DFEATURE_gui=OFF",
            "-DFEATURE_widgets=OFF",
            "-DFEATURE_printsupport=OFF",
            "-DFEATURE_testlib=OFF",
            "-DFEATURE_sql=ON",
            "-DFEATURE_dbus=OFF",
            "-DFEATURE_icu=OFF",
            "-DFEATURE_glib=OFF",
            "-DFEATURE_system_zlib=ON",
            "-DFEATURE_openssl=ON",
            "-DFEATURE_openssl_linked=ON",
            "-DINPUT_openssl=linked",
            "-DFEATURE_system_openjpeg=OFF",
            "-DFEATURE_system_jpeg=OFF",
            "-DFEATURE_system_png=OFF",
            "-DFEATURE_system_harfbuzz=OFF",
            "-DFEATURE_system_pcre2=OFF",
            "-DFEATURE_system_doubleconversion=OFF",
            "-DFEATURE_system_textmarkdown=OFF",
            "-DFEATURE_reduce_relocations=OFF",
            "-DFEATURE_brotli=ON",
        ]

    def build(self) -> None:
        print(f"Building {self.name} {self.version}")
        cmd = self.commander
        env = self.tc.cmake_env
        prefix = str(self.tc.install_prefix)
        build_dir = self.src_dir / "build"

        configure_args = [
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_SHARED_LIBS=OFF",
            "-DFEATURE_shared=OFF",
            "-DFEATURE_gui=OFF",
            "-DFEATURE_widgets=OFF",
            "-DFEATURE_printsupport=OFF",
            "-DFEATURE_testlib=OFF",
            "-DFEATURE_sql=ON",
            "-DFEATURE_dbus=OFF",
            "-DFEATURE_icu=OFF",
            "-DFEATURE_glib=OFF",
            "-DFEATURE_system_zlib=ON",
            f"-DZLIB_ROOT={self.tc.dep_prefix('zlib')}",
            "-DFEATURE_openssl=ON",
            "-DFEATURE_openssl_linked=ON",
            f"-DOPENSSL_ROOT_DIR={self.tc.dep_prefix('openssl')}",
            "-DINPUT_openssl=linked",
            "-DFEATURE_system_openjpeg=OFF",
            "-DFEATURE_system_jpeg=OFF",
            "-DFEATURE_system_png=OFF",
            "-DFEATURE_system_harfbuzz=OFF",
            "-DFEATURE_system_pcre2=OFF",
            "-DFEATURE_system_doubleconversion=OFF",
            "-DFEATURE_system_textmarkdown=OFF",
            "-DFEATURE_reduce_relocations=OFF",
            "-DFEATURE_brotli=ON",
        ]

        cmd.run(
            [
                self.tc.cmake_bin,
                "-B",
                str(build_dir),
                *self.tc.cmake_common_args,
                f"-DCMAKE_INSTALL_PREFIX={prefix}",
                *configure_args,
                "-S",
                str(self.src_dir),
            ],
            env=env,
        )
        cmd.run(
            [self.tc.cmake_bin, "--build", str(build_dir), *cmd.nproc_args()],
            env=env,
        )
        cmd.run(
            [self.tc.cmake_bin, "--install", str(build_dir)],
            env=env,
        )
        print(f"Built {self.name} {self.version}")
