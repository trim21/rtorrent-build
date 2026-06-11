"""OpenSSL builder."""

from ..manifest import LibInfo
from ..run import Commander
from ..toolchain import Builder, ResolvedSource, Toolchain


class OpensslBuilder(Builder):
    def __init__(
        self, toolchain: Toolchain, lib: LibInfo, source: ResolvedSource, commander: Commander
    ) -> None:
        self.tc = toolchain
        self.name = source.name
        self.version = source.version
        self.src_dir = source.src_dir
        self.commander = commander

    def cache_key_extra(self) -> list[str]:
        return super().cache_key_extra() + ["no-shared", "no-dso", "no-tests", "linux-x86_64"]

    def build(self) -> None:
        print(f"Building {self.name} {self.version}")
        env = self.tc.env
        cmd = self.commander

        zig_cc = " ".join(self.tc.zig_cc)
        zig_cxx = " ".join(self.tc.zig_cxx)
        zig_ar = " ".join(self.tc.zig_ar)
        zig_ranlib = " ".join(self.tc.zig_ranlib)

        configure_args = [
            f"--prefix={self.tc.install_prefix}",
            "no-shared",
            "no-dso",
            "no-tests",
            "linux-x86_64",
        ]

        cmd.run(
            [
                "perl",
                "Configure",
                *configure_args,
            ],
            cwd=str(self.src_dir),
            env={
                **env,
                "CC": zig_cc,
                "CXX": zig_cxx,
                "AR": zig_ar,
                "RANLIB": zig_ranlib,
            },
        )
        cmd.run(
            ["make", *cmd.nproc_args()],
            cwd=str(self.src_dir),
            env=env,
        )
        cmd.run(
            ["make", "install_sw"],
            cwd=str(self.src_dir),
            env=env,
        )
        print(f"Built {self.name} {self.version}")
