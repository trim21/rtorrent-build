"""rtorrent builder module."""

import re

from .._options import RtorrentOptions
from ..manifest import LibInfo
from ..run import Commander
from ..toolchain import Builder, ResolvedSource, Toolchain
from ..utils import replace_in_file


def _semver(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (9999,)


class RtorrentBuilder(Builder):
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

    def build(self) -> None:
        self._autoreconf()

        print(f"Building {self.name} {self.version}")
        env = self.tc.env
        cmd = self.commander

        configure_args = [
            "./configure",
            f"--prefix={self.tc.install_prefix}",
            "--disable-shared",
            "--enable-static",
        ]
        if self.tc.debug:
            configure_args.append("--enable-debug")
        else:
            configure_args.append("--disable-debug")

        has_curses_stub = (self.src_dir / "src" / "display" / "curses_stub.h").exists()
        wants_ncurses = self.lib.requires is not None and "ncurses" in self.lib.requires

        if wants_ncurses:
            configure_args.append("--with-ncursesw")
        elif has_curses_stub:
            configure_args.append("--without-ncurses")
        else:
            configure_args.append("--with-ncursesw")

        v = _semver(self.version)
        if v >= (0, 16):
            configure_args += [
                "--with-xmlrpc-tinyxml2",
                "--with-lua",
            ]

        lua_prefix = self.tc.dep_prefix("lua")

        cppflags = env["CPPFLAGS"]
        if wants_ncurses:
            cppflags += " -DNCURSES_WIDECHAR"

        make_env = {
            **env,
            "CPPFLAGS": cppflags,
            "PATH": f"{lua_prefix}/bin:{env['PATH']}",
        }

        if self.lib.cxx_std:
            make_env["CXXFLAGS"] = f"{env['CXXFLAGS']} -std={self.lib.cxx_std}"

        cmd.run(configure_args, cwd=str(self.src_dir), env=make_env)

        if self._opts.ua:
            config_h = self.src_dir / "config.h"
            replace_in_file(
                config_h,
                re.compile(r"^#define USER_AGENT .*$", re.MULTILINE),
                f'#define USER_AGENT std::string("{self._opts.ua}")',
            )

        cmd.run(
            ["make", *cmd.nproc_args()],
            cwd=str(self.src_dir),
            env=make_env,
        )
        cmd.run(
            ["make", "install"],
            cwd=str(self.src_dir),
            env=make_env,
        )
