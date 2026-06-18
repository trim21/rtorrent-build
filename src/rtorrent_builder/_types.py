"""Shared types for rtorrent builder."""

import os
from enum import Enum

IN_CI = os.environ.get("CI", "").lower() in {"1", "yes", "true"}


class Libc(Enum):
    """Target libc for the build."""

    glibc = "glibc"
    musl = "musl"


class Arch(Enum):
    """x86-64 microarchitecture level."""

    v1 = "amd/v1"
    v2 = "amd/v2"
    v3 = "amd/v3"
    v4 = "amd/v4"
    native = "native"

    @property
    def march(self) -> str:
        """GCC/clang ``-march`` flag value (LLVM underscore form)."""
        if self == Arch.native:
            return "native"
        return {
            Arch.v1: "x86_64",
            Arch.v2: "x86_64_v2",
            Arch.v3: "x86_64_v3",
            Arch.v4: "x86_64_v4",
        }[self]

    @property
    def safe(self) -> str:
        """Filesystem-safe variant (``.`` instead of ``/``)."""
        return self.value.replace("/", ".")
