"""rtorrent-meson builder module — builds the trim21/rtorrent monorepo."""

import hashlib

from ._meson import MesonBuilder


class RtorrentMesonBuilder(MesonBuilder):
    def meson_args(self, prefix: str) -> list[str]:
        return []

    @property
    def cache_key_extra(self) -> list[str]:
        extra = super().cache_key_extra
        lua_patch = self.tc.patches_dir / "lua-ok-compat.patch"
        if lua_patch.exists():
            extra.append("patch:lua-ok:" + hashlib.sha256(lua_patch.read_bytes()).hexdigest())
        return extra

    def build(self) -> None:
        lua_patch = self.tc.patches_dir / "lua-ok-compat.patch"
        if lua_patch.exists():
            self.commander.run(
                ["git", "apply", "-p1", str(lua_patch)],
                cwd=str(self.src_dir),
            )
        super().build()
