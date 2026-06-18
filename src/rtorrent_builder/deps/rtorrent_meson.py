"""rtorrent-meson builder module — builds the trim21/rtorrent monorepo."""

from pathlib import Path

from ._meson import MesonBuilder


class RtorrentMesonBuilder(MesonBuilder):
    default_deps: list[str] = ["openssl", "zlib", "curl", "luajit"]

    @property
    def patches_dir(self) -> Path:
        return Path(__file__).parent / "patches" / "rtorrent-meson"

    def meson_args(self, prefix: str) -> list[str]:
        return []
