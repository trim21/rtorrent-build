"""qbittorrent-nox builder (CMake, headless)."""

from __future__ import annotations

from ..utils import replace_in_file
from ._cmake import CMakeBuilder


class QbittorrentBuilder(CMakeBuilder):
    default_deps: list[str] = [
        "zlib",
        "openssl",
        "boost",
        "libtorrent-rasterbar",
        "qtbase",
        "qttools",
    ]

    def cmake_args(self) -> list[str]:
        return [
            "-DCMAKE_CXX_STANDARD=20",
            "-DGUI=OFF",
            "-DWEBUI=ON",
        ]

    def build(self) -> None:
        replace_in_file(
            self.src_dir / "src/base/http/requestparser.cpp",
            "    const QByteArray EOH = CRLF.repeated(2);\n",
            '    const QByteArray EOH = QByteArrayLiteral("\\x0D\\x0A").repeated(2);\n',
        )
        super().build()
