from ._make import MakeBuilder


class Libidn2Builder(MakeBuilder):
    def configure(self) -> None:
        self.commander.run(
            [
                "./configure",
                f"--prefix={self.tc.install_prefix}",
                "--disable-shared",
                "--enable-static",
                "--disable-doc",
                "--disable-gcc-warnings",
            ],
            cwd=str(self.src_dir),
            env=self.build_env,
        )

    def make_args(self) -> list[str]:
        return self.commander.nproc_args()

    def install_args(self) -> list[str]:
        return ["install"]
