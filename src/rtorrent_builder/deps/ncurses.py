from ._make import MakeBuilder


class NcursesBuilder(MakeBuilder):
    @property
    def cache_key_extra(self) -> list[str]:
        return [
            "--enable-static",
            "--disable-shared",
            "--with-termlib",
            "--with-normal",
            "--with-cxx",
            "--with-cxx-binding",
            "--enable-pc-files",
            "--with-static",
            "--without-shared",
            "--enable-widec",
            "--without-progs",
            "--without-tests",
        ]

    def configure(self) -> None:
        self.tc.commander.run(
            [
                "./configure",
                f"--prefix={self.tc.install_prefix}",
                "--enable-static",
                "--disable-shared",
                "--with-termlib",
                "--with-normal",
                "--with-cxx",
                "--with-cxx-binding",
                f"--with-default-terminfo-dir={self.tc.install_prefix}/share/terminfo",
                "--enable-pc-files",
                f"--with-pkg-config-libdir={self.tc.install_prefix}/lib/pkgconfig",
                "--with-static",
                "--without-shared",
                "--enable-widec",
                "--without-progs",
                "--without-tests",
            ],
            cwd=str(self.src_dir),
            env=self.build_env,
        )

    def make_args(self) -> list[str]:
        return self.tc.commander.nproc_args()

    def install_args(self) -> list[str]:
        return ["install"]
