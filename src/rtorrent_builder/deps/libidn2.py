from ._make import MakeBuilder


class Libidn2Builder(MakeBuilder):
    def configure(self) -> None:
        if self.tc.shared_deps:
            static_flag = "--disable-static"
            shared_flag = "--enable-shared"
        else:
            static_flag = "--enable-static"
            shared_flag = "--disable-shared"
        self.commander.run(
            [
                "./configure",
                f"--prefix={self.tc.install_prefix}",
                shared_flag,
                static_flag,
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
