from ._make import MakeBuilder


class LibunistringBuilder(MakeBuilder):
    default_deps: list[str] = []

    def configure(self) -> None:
        self.commander.run(
            [
                "./configure",
                f"--prefix={self.tc.install_prefix}",
                "--disable-dependency-tracking",
                "--disable-shared",
                "--enable-static",
            ],
            cwd=str(self.src_dir),
            env=self.build_env,
        )

    def make_args(self) -> list[str]:
        return self.commander.nproc_args()

    def install_args(self) -> list[str]:
        return ["install"]
