"""libtorrent builder."""

import re

from .._options import LibtorrentOptions
from ..manifest import LibInfo
from ..run import Commander
from ..toolchain import Builder, ResolvedSource, Toolchain
from ..utils import replace_in_file


class LibtorrentBuilder(Builder):
    def __init__(
        self, toolchain: Toolchain, lib: LibInfo, source: ResolvedSource, commander: Commander
    ) -> None:
        self.tc = toolchain
        self.lib = lib
        self.name = source.name
        self.version = source.version
        self.src_dir = source.src_dir
        self._opts = LibtorrentOptions.from_options(toolchain.options)
        self.commander = commander

    def cache_key_extra(self) -> list[str]:
        return super().cache_key_extra() + self._opts.cache_key()

    def _autoreconf(self) -> None:
        """Run autoreconf -ivf if ./configure is missing (e.g. master branch archive)."""
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
        env = dict(self.tc.env)
        cmd = self.commander

        if self.lib.cxx_std:
            env["CXXFLAGS"] = f"{env['CXXFLAGS']} -std={self.lib.cxx_std}"

        configure_args = [
            "./configure",
            f"--prefix={self.tc.install_prefix}",
            f"--with-zlib={self.tc.dep_prefix('zlib')}",
            "--disable-shared",
            "--enable-static",
        ]
        if self.tc.debug:
            configure_args.append("--enable-debug")
        else:
            configure_args.append("--disable-debug")

        cmd.run(configure_args, cwd=str(self.src_dir), env=env)

        if self._opts.peer_name:
            config_h = self.src_dir / "config.h"
            replace_in_file(
                config_h,
                re.compile(r'^#define PEER_NAME ".*?"$', re.MULTILINE),
                f'#define PEER_NAME "{self._opts.peer_name}"',
            )

        cmd.run(
            ["make", *cmd.nproc_args()],
            cwd=str(self.src_dir),
            env=env,
        )
        cmd.run(
            ["make", "install"],
            cwd=str(self.src_dir),
            env=env,
        )
        pc_file = self.tc.install_prefix / "lib" / "pkgconfig" / "libtorrent.pc"
        if pc_file.exists():
            ac = self.src_dir / "configure.ac"
            if ac.exists() and "LIBCURL" in ac.read_text():
                replace_in_file(
                    pc_file,
                    "Requires.private: zlib, libcrypto\n",
                    "Requires.private: zlib, libcrypto, libcurl\n",
                    required=False,
                )
        print(f"Built {self.name} {self.version}")
