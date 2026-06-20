"""Qt 6 (qtbase) builder for headless/static builds."""

from __future__ import annotations

from ._cmake import CMakeBuilder


class QtBaseBuilder(CMakeBuilder):
    default_deps: list[str] = ["zlib", "openssl", "zstd", "brotli"]

    def cmake_args(self) -> list[str]:
        return [
            "-DCMAKE_BUILD_TYPE=Release",
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
