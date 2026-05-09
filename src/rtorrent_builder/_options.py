"""Per-package build options dataclasses."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RtorrentOptions:
    disguise: bool = False

    @classmethod
    def from_options(cls, options: dict[str, str]) -> "RtorrentOptions":
        return cls(disguise=options.get("rtorrent.disguise") == "1")

    def cache_key(self) -> list[str]:
        extra: list[str] = []
        if self.disguise:
            extra.append("disguise")
        return extra

    @property
    def ua(self) -> str | None:
        if self.disguise:
            return "rtorrent/0.9.8/0.13.8"
        return None


@dataclass(frozen=True)
class LibtorrentOptions:
    disguise: bool = False

    @classmethod
    def from_options(cls, options: dict[str, str]) -> "LibtorrentOptions":
        return cls(disguise=options.get("rtorrent-libtorrent.disguise") == "1")

    def cache_key(self) -> list[str]:
        extra: list[str] = []
        if self.disguise:
            extra.append("disguise")
        return extra

    @property
    def peer_name(self) -> str | None:
        if self.disguise:
            return "-lt0D80-"
        return None
