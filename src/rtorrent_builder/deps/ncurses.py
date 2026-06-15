from ._make import MakeBuilder


class NcursesBuilder(MakeBuilder):
    def _shared_args(self) -> list[str]:
        if self.tc.shared_deps:
            return [
                "--disable-static",
                "--enable-shared",
                "--without-static",
                "--with-shared",
            ]
        return [
            "--enable-static",
            "--disable-shared",
            "--with-static",
            "--without-shared",
        ]

    def cache_key_extra(self) -> list[str]:
        return super().cache_key_extra() + [
            *self._shared_args(),
            "--with-termlib",
            "--with-normal",
            "--with-cxx",
            "--with-cxx-binding",
            "--enable-pc-files",
            "--enable-widec",
            "--without-progs",
            "--without-tests",
        ]

    def configure(self) -> None:
        self.commander.run(
            [
                "./configure",
                f"--prefix={self.tc.install_prefix}",
                "--with-build-cc=cc",
                "--with-build-cflags=-O2",
                *self._shared_args(),
                "--with-termlib",
                "--with-normal",
                "--with-cxx",
                "--with-cxx-binding",
                f"--with-default-terminfo-dir={self.tc.install_prefix}/share/terminfo",
                "--enable-pc-files",
                f"--with-pkg-config-libdir={self.tc.install_prefix}/lib/pkgconfig",
                "--enable-widec",
                "--without-progs",
                "--without-tests",
            ],
            cwd=str(self.src_dir),
            env=self.build_env,
        )

    def make_args(self) -> list[str]:
        return self.commander.nproc_args()

    def install_args(self) -> list[str]:
        return ["install"]
