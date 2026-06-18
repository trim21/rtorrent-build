from __future__ import annotations

from ._cmake import CMakeBuilder


class TransmissionBuilder(CMakeBuilder):
    default_deps: list[str] = ["openssl", "curl", "libdeflate"]

    def cmake_args(self) -> list[str]:
        return [
            "-DENABLE_CLI=OFF",
            "-DENABLE_TESTS=OFF",
            "-DENABLE_GTK=OFF",
            "-DENABLE_QT=OFF",
            "-DENABLE_MAC=OFF",
            "-DENABLE_UTILS=OFF",
            "-DENABLE_NLS=OFF",
            "-DENABLE_DAEMON=ON",
            "-DWITH_CRYPTO=openssl",
            "-DUSE_SYSTEM_EVENT2=OFF",
            "-DUSE_SYSTEM_DEFLATE=ON",
            "-DUSE_SYSTEM_DHT=OFF",
            "-DUSE_SYSTEM_MINIUPNPC=OFF",
            "-DUSE_SYSTEM_NATPMP=OFF",
            "-DUSE_SYSTEM_PSL=OFF",
            "-DUSE_SYSTEM_B64=OFF",
            "-DUSE_SYSTEM_UTP=OFF",
            "-DUSE_SYSTEM_FAST_FLOAT=OFF",
            "-DUSE_SYSTEM_FMT=OFF",
            "-DUSE_SYSTEM_SMALL=OFF",
            "-DUSE_SYSTEM_UTF8CPP=OFF",
            "-DUSE_SYSTEM_WIDE_INTEGER=OFF",
            "-DUSE_SYSTEM_SIGSLOT=OFF",
            "-DREBUILD_WEB=OFF",
            "-DINSTALL_DOC=OFF",
            "-DINSTALL_LIB=OFF",
        ]
