"""rtorrent builder module."""

import re

from packaging.version import Version

from .._options import RtorrentOptions
from ..manifest import LibInfo
from ..run import Commander
from ..toolchain import Builder, ResolvedSource, Toolchain
from ..utils import conditional_args, parse_version, replace_in_file


class RtorrentBuilder(Builder):
    default_deps: list[str] = ["rtorrent-libtorrent"]

    def __init__(
        self, toolchain: Toolchain, lib: LibInfo, source: ResolvedSource, commander: Commander
    ) -> None:
        self.tc = toolchain
        self.lib = lib
        self.name = source.name
        self.version = source.version
        self.src_dir = source.src_dir
        self._opts = RtorrentOptions.from_options(toolchain.options)
        self.commander = commander

    def cache_key_extra(self) -> list[str]:
        return super().cache_key_extra() + self._opts.cache_key()

    def _autoreconf(self) -> None:
        if (self.src_dir / "configure").exists():
            return
        print(f"configure script not found, running autoreconf -ivf in {self.src_dir}")
        self.commander.run(
            ["autoreconf", "-ivf"],
            cwd=str(self.src_dir),
            env=self.tc.env,
        )

    def _build_env(self) -> dict[str, str]:
        env = self.tc.env
        cppflags = env["CPPFLAGS"]
        wants_ncurses = self.lib.requires is not None and "ncurses" in self.lib.requires
        if wants_ncurses:
            cppflags += " -DNCURSES_WIDECHAR"

        make_env = {
            **env,
            "CPPFLAGS": cppflags,
            "PATH": f"{self.tc.dep_prefix('lua')}/bin:{env['PATH']}",
        }
        if self.lib.cxx_std:
            make_env["CXXFLAGS"] = f"{env['CXXFLAGS']} -std={self.lib.cxx_std}"
        return make_env

    def generate(self) -> None:
        self._autoreconf()

        print(f"Generating {self.name} {self.version}")
        cmd = self.commander

        has_curses_stub = (self.src_dir / "src" / "display" / "curses_stub.h").exists()
        wants_ncurses = self.lib.requires is not None and "ncurses" in self.lib.requires
        v = parse_version(self.version)

        configure_args = conditional_args({
            "./configure": True,
            f"--prefix={self.tc.install_prefix}": True,
            "--disable-dependency-tracking": True,
            "--disable-shared": True,
            "--enable-static": True,
            "--enable-debug": self.tc.debug,
            "--disable-debug": not self.tc.debug,
            "--with-ncursesw": wants_ncurses or not has_curses_stub,
            "--without-ncurses": not wants_ncurses and has_curses_stub,
            "--with-xmlrpc-tinyxml2": v >= Version("0.16"),
            "--with-lua": v >= Version("0.16"),
        })

        cmd.run(configure_args, cwd=str(self.src_dir), env=self._build_env())

        if self._opts.ua:
            config_h = self.src_dir / "config.h"
            replace_in_file(
                config_h,
                re.compile(r"^#define USER_AGENT .*$", re.MULTILINE),
                f'#define USER_AGENT std::string("{self._opts.ua}")',
            )

    def build(self) -> None:
        self.commander.run(
            ["make", *self.commander.nproc_args()],
            cwd=str(self.src_dir),
            env=self._build_env(),
        )

    def install(self) -> None:
        self.commander.run(
            ["make", "install"],
            cwd=str(self.src_dir),
            env=self._build_env(),
        )
