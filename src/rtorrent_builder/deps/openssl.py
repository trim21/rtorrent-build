"""OpenSSL builder."""

from ._make import MakeBuilder


class OpensslBuilder(MakeBuilder):
    default_deps: list[str] = []

    def cache_key_extra(self) -> list[str]:
        return super().cache_key_extra() + [
            "no-shared",
            "no-dso",
            "no-tests",
            "linux-x86_64",
            "openssldir=/etc/ssl",
        ]

    def configure(self) -> None:
        self.commander.run(
            [
                "perl",
                "Configure",
                f"--prefix={self.tc.install_prefix}",
                "--openssldir=/etc/ssl",
                "no-shared",
                "no-dso",
                "no-tests",
                "linux-x86_64",
            ],
            cwd=str(self.src_dir),
            env=self.build_env,
        )

    def make_args(self) -> list[str]:
        return self.commander.nproc_args()

    def install_args(self) -> list[str]:
        return ["install_sw"]
