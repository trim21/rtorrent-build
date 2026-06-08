"""Toolchain setup: zig compiler + cmake from PyPI, targeting old glibc or musl."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tarfile
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from . import PROJECT_ROOT as _PROJECT_ROOT
from ._types import Arch, Libc
from .download import download_file
from .manifest import (
    GitHubRefSource,
    GitHubReleaseSource,
    GitHubTagSource,
    LibInfo,
    Lock,
    URLSource,
    load_lock,
)
from .run import Commander


@dataclass(frozen=True, kw_only=True)
class ResolvedSource:
    name: str
    version: str
    src_dir: Path


class Builder(ABC):
    @abstractmethod
    def __init__(
        self, toolchain: Toolchain, lib: LibInfo, source: ResolvedSource, commander: Commander
    ) -> None: ...

    @abstractmethod
    def build(self) -> None: ...

    @property
    def cache_key_extra(self) -> list[str]:
        return []


class Toolchain:
    def __init__(
        self,
        variant: str,
        toolchain: str,
        work_dir: Path,
        project_root: Path | None = None,
        glibc_target: str = "2.17",
        options: dict[str, str] | None = None,
        libc: Libc = Libc.glibc,
        arch: Arch = Arch.v1,
        debug: bool = False,
    ) -> None:
        self.variant = variant
        self._toolchain_name = toolchain
        self.work_dir = work_dir
        self._project_root = project_root or _PROJECT_ROOT
        self._glibc_target = glibc_target
        self.options: dict[str, str] = options or {}
        self.libc = libc
        self.arch = arch
        self.debug = debug

        self.install_prefix = work_dir / "install"
        self.build_dir = work_dir / "build"
        self.package_dir = self._project_root / "assets"
        self.venv_dir = self._project_root / "toolchains" / toolchain / ".venv"
        self.marker_dir = work_dir / ".markers"

        self._validate_toolchain_marker()

        for d in [
            self.install_prefix,
            self.build_dir,
            self.package_dir,
            self.install_prefix / "bin",
            self.install_prefix / "lib",
            self.install_prefix / "lib64",
        ]:
            d.mkdir(parents=True, exist_ok=True)

        self._log_dir = work_dir / "logs"
        self._commander = Commander(work_dir / "prepare.log")

    def make_commander(self, name: str) -> Commander:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        return Commander(self._log_dir / f"{name}.log")

    def dep_prefix(self, dep_name: str) -> Path:
        return self.install_prefix

    @cached_property
    def _lock(self) -> Lock:
        return load_lock(self._project_root / "manifests" / f"{self.variant}.jsonc")

    def _resolve_git_sha(self, source: GitHubRefSource) -> str:
        resolved_tag = self._lock.resolved_tag(source.github, source.ref)
        if resolved_tag:
            sha = self._lock.sha(source.github, resolved_tag)
            if sha:
                return sha
        sha = self._lock.sha(source.github, source.ref)
        if sha is None:
            raise RuntimeError(
                f"Git source {source.github}#{source.ref} not found in lockfile — "
                "run 'uv run python scripts/lock.py' to regenerate"
            )
        return sha

    def prepare_source(self, name: str, lib: LibInfo) -> ResolvedSource:
        if isinstance(lib.source, GitHubRefSource):
            return self._prepare_git_source(name, lib.source)
        if isinstance(lib.source, (GitHubTagSource, GitHubReleaseSource)):
            msg = f"{type(lib.source).__name__} should be resolved to URLSource via lockfile first"
            raise TypeError(msg)
        if isinstance(lib.source, URLSource):
            return self._prepare_url_source(name, lib.source, lib.version)
        raise TypeError(f"Unsupported source type: {type(lib.source)}")

    @staticmethod
    def _archive_ext(url: str) -> str:
        suffixes = Path(url).suffixes
        if len(suffixes) >= 2 and suffixes[-2] == ".tar":
            return suffixes[-2] + suffixes[-1]
        return suffixes[-1] if suffixes else ".tar.gz"

    @staticmethod
    def _archive_prefix(archive: Path) -> str:
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as zf:
                return os.path.commonpath(zf.namelist())
        with tarfile.open(archive) as tf:
            return os.path.commonpath(tf.getnames())

    def clean_source(self, name: str, lib: LibInfo) -> None:
        if isinstance(lib.source, URLSource):
            ext = self._archive_ext(lib.source.url)
            tarball = self.package_dir / f"{name}-{lib.version}{ext}"
            if not tarball.exists():
                return
            prefix = self._archive_prefix(tarball)
            src_dir = self.build_dir / prefix
            if src_dir.exists():
                print(f"Cleaning source dir: {src_dir}")
                shutil.rmtree(src_dir)
        elif isinstance(lib.source, (GitHubRefSource, GitHubTagSource, GitHubReleaseSource)):
            for d in self.build_dir.glob(f"{name}-*"):
                if d.is_dir():
                    print(f"Cleaning source dir: {d}")
                    shutil.rmtree(d)

    def _prepare_url_source(self, name: str, source: URLSource, version: str) -> ResolvedSource:
        archive = self.package_dir / f"{name}-{version}{self._archive_ext(source.url)}"

        if not archive.exists():
            download_file(source.url, archive, desc=f"{name}-{version}")

        prefix = self._archive_prefix(archive)
        src_dir = self.build_dir / prefix

        if src_dir.exists():
            print(f"Source already extracted: {src_dir}")
            return ResolvedSource(name=name, version=version, src_dir=src_dir)

        print(f"Extracting {archive}")
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(path=self.build_dir)
        else:
            with tarfile.open(archive) as tf:
                tf.extractall(path=self.build_dir, filter="data")

        return ResolvedSource(name=name, version=version, src_dir=src_dir)

    def _prepare_git_source(self, name: str, source: GitHubRefSource) -> ResolvedSource:
        full_sha = self._resolve_git_sha(source)
        short_sha = full_sha[:7]

        clone_dir = self.work_dir / "sources" / name

        if not (clone_dir / ".git").exists():
            clone_dir.parent.mkdir(parents=True, exist_ok=True)
            print(f"Cloning {source.github}...")
            self._commander.run(["git", "clone", source.github, str(clone_dir)])

        print(f"Fetching {full_sha} from {source.github}...")
        self._commander.run(["git", "-C", str(clone_dir), "fetch", "--prune", "origin", full_sha])

        tarball = self.package_dir / f"{name}-{full_sha}.tar.gz"
        src_dir = self.build_dir / f"{name}-{full_sha}"

        if not src_dir.exists():
            if not tarball.exists():
                print(f"Creating archive {tarball}")
                self._commander.run(
                    [
                        "git",
                        "-C",
                        str(clone_dir),
                        "archive",
                        "--format=tar.gz",
                        f"--prefix={name}-{full_sha}/",
                        "-o",
                        str(tarball),
                        full_sha,
                    ]
                )

            print(f"Extracting {tarball}")
            with tarfile.open(tarball) as tf:
                tf.extractall(path=self.build_dir, filter="data")

        return ResolvedSource(name=name, version=short_sha, src_dir=src_dir)

    @property
    def _target_triple(self) -> str:
        if self.libc == Libc.musl:
            return "x86_64-linux-musl"
        base = "x86_64-linux-gnu"
        if self._glibc_target:
            return f"{base}.{self._glibc_target}"
        return base

    def _write_wrappers(self) -> None:
        wd = self.work_dir / "wrappers"
        wd.mkdir(parents=True, exist_ok=True)

        for name, args in [
            ("zig-cc", f"cc -target {self._target_triple}"),
            ("zig-c++", f"c++ -target {self._target_triple}"),
            ("zig-ar", "ar"),
            ("zig-ranlib", "ranlib"),
        ]:
            wrapper = wd / name
            wrapper.write_text(f'#!/bin/sh\nexec "{self.zig_bin}" {args} "$@"\n')
            wrapper.chmod(0o755)

    def setup(self) -> None:
        toolchain_dir = self._project_root / "toolchains" / self._toolchain_name
        toolchain_pyproject = toolchain_dir / "pyproject.toml"
        if not toolchain_pyproject.exists():
            print(f"ERROR: toolchain pyproject not found: {toolchain_pyproject}")
            raise FileNotFoundError(f"Missing {toolchain_pyproject}")

        print(f"Syncing toolchain for {self.variant} at {toolchain_dir}")
        sync_env = os.environ | {"VIRTUAL_ENV": str(self.venv_dir)}
        self._commander.run(
            ["uv", "sync", "--no-install-project"],
            cwd=str(toolchain_dir),
            env=sync_env,
        )
        print(f"Toolchain synced at {self.venv_dir}")
        self._write_wrappers()

    @property
    def _toolchain_marker_name(self) -> str:
        marker = f".tc-{self.libc.value}-{self.arch.safe}"
        if self.libc == Libc.glibc:
            marker += f".{self._glibc_target}"
        if self.debug:
            marker += ".debug"
        return marker

    def _validate_toolchain_marker(self) -> None:
        tc_marker = self.marker_dir / self._toolchain_marker_name
        if not tc_marker.exists():
            if self.work_dir.exists():
                shutil.rmtree(self.work_dir)
            self.marker_dir.mkdir(parents=True, exist_ok=True)
            tc_marker.touch()

    def _marker_path(self, name: str, version: str, features: list[str] | None = None) -> Path:
        features = features or []
        h = hashlib.blake2b(repr(sorted(features)).encode(), digest_size=4).hexdigest()
        return self.marker_dir / f"{name}-{version}-{h}"

    def is_built(self, name: str, version: str, features: list[str] | None = None) -> bool:
        return self._marker_path(name, version, features).exists()

    def mark_built(self, name: str, version: str, features: list[str] | None = None) -> None:
        self.marker_dir.mkdir(parents=True, exist_ok=True)
        self._marker_path(name, version, features).touch()

    @cached_property
    def zig_bin(self) -> str:
        for lib_dir in (self.venv_dir / "lib", self.venv_dir / "lib64"):
            if not lib_dir.exists():
                continue
            for d in sorted(lib_dir.iterdir()):
                if d.name.startswith("python3"):
                    zig = d / "site-packages" / "ziglang" / "zig"
                    if zig.exists():
                        return str(zig)
        raise FileNotFoundError(f"zig binary not found under {self.venv_dir}")

    @cached_property
    def zig_version(self) -> str:
        result = subprocess.run(
            [self.zig_bin, "version"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    @property
    def cmake_bin(self) -> str:
        return str(self.venv_dir / "bin" / "cmake")

    @property
    def zig_cc(self) -> list[str]:
        return [self.zig_bin, "cc", "-target", self._target_triple]

    @property
    def zig_cxx(self) -> list[str]:
        return [self.zig_bin, "c++", "-target", self._target_triple]

    @property
    def zig_ar(self) -> list[str]:
        return [self.zig_bin, "ar"]

    @property
    def zig_ranlib(self) -> list[str]:
        return [self.zig_bin, "ranlib"]

    @cached_property
    def _zig_lib_dir(self) -> Path:
        lib = Path(self.zig_bin).parent / "lib"
        if lib.exists():
            return lib
        raise FileNotFoundError(f"ziglang lib not found at {lib}")

    def _zig_include_dirs(self, lang: str) -> str:
        lib = self._zig_lib_dir
        target = self._target_triple
        arch = target.split("-")[0]
        libc_variant = "musl" if "musl" in target else "glibc"
        libc_arch = target.split("-linux-")[1].split(".")[0]

        dirs = [
            str(lib / "libcxx" / "include"),
            str(lib / "libcxxabi" / "include"),
            str(lib / "include"),
            str(lib / "libc" / "include" / f"{arch}-linux-{libc_arch}"),
            str(lib / "libc" / "include" / f"generic-{libc_variant}"),
            str(lib / "libc" / "include" / f"{arch}-linux-any"),
            str(lib / "libc" / "include" / "any-linux-any"),
        ]
        if lang == "c++":
            dirs.append(str(lib / "libunwind" / "include"))
        return ";".join(dirs)

    def _write_toolchain_file(self) -> Path:
        path = self.work_dir / "zig-toolchain.cmake"
        install_lib = str(self.install_prefix / "lib")
        install_lib64 = str(self.install_prefix / "lib64")
        wd = str(self.work_dir / "wrappers")
        if self.debug:
            cmake_cflags = "-fPIC -g -O0 -w"
            cmake_ldflags = f"-L{install_lib} -L{install_lib64}"
        else:
            cmake_cflags = "-fPIC -flto -w"
            cmake_ldflags = f"-flto -L{install_lib} -L{install_lib64}"

        content = "\n".join(
            [
                "cmake_policy(SET CMP0167 NEW)",
                "",
                f'set(CMAKE_C_COMPILER "{wd}/zig-cc")',
                f'set(CMAKE_CXX_COMPILER "{wd}/zig-c++")',
                f'set(CMAKE_ASM_COMPILER "{wd}/zig-cc")',
                f'set(CMAKE_AR "{wd}/zig-ar")',
                f'set(CMAKE_RANLIB "{wd}/zig-ranlib")',
                "",
                f'set(CMAKE_C_FLAGS_INIT "{cmake_cflags}")',
                f'set(CMAKE_CXX_FLAGS_INIT "{cmake_cflags}")',
                f'set(CMAKE_EXE_LINKER_FLAGS_INIT "{cmake_ldflags}")',
                "",
                'set(HAVE_FILE_OFFSET_BITS 0 CACHE INTERNAL "")',
                "",
                f'set(CMAKE_C_IMPLICIT_INCLUDE_DIRECTORIES "{self._zig_include_dirs("cc")}")',
                f'set(CMAKE_CXX_IMPLICIT_INCLUDE_DIRECTORIES "{self._zig_include_dirs("c++")}")',
                'set(CMAKE_SYSTEM_IGNORE_PATH "/usr/include")',
                "",
            ]
        )
        path.write_text(content)
        return path

    @property
    def cmake_common_args(self) -> list[str]:
        return [
            "-G",
            "Ninja",
            "-DCMAKE_TOOLCHAIN_FILE=" + str(self._write_toolchain_file()),
        ]

    @property
    def env(self) -> dict[str, str]:
        zig_cc_str = " ".join(self.zig_cc)
        zig_cxx_str = " ".join(self.zig_cxx)
        install_lib = str(self.install_prefix / "lib")
        install_include = str(self.install_prefix / "include")

        if self.debug:
            ldflags = f"-L{install_lib} -L{install_lib}64"
            cflags = f"-fPIC -g -O0 -w -march={self.arch.march}"
        else:
            ldflags = f"-flto -L{install_lib} -L{install_lib}64"
            cflags = f"-fPIC -Os -g -flto -w -march={self.arch.march}"
        if self.libc == Libc.musl:
            ldflags += " -static"
            cflags += " -static"

        pkg_path = f"{install_lib}/pkgconfig:{install_lib}64/pkgconfig"
        return os.environ | {
            "CC": zig_cc_str,
            "CXX": zig_cxx_str,
            "AR": " ".join(self.zig_ar),
            "RANLIB": " ".join(self.zig_ranlib),
            "STRIP": f"{self.zig_bin} strip",
            "CPPFLAGS": f"-I{install_include}",
            "CFLAGS": cflags,
            "CXXFLAGS": cflags,
            "LDFLAGS": ldflags,
            "PKG_CONFIG": "pkg-config --static",
            "PKG_CONFIG_PATH": pkg_path,
            "PKG_CONFIG_LIBDIR": pkg_path,
            "PATH": f"{self.venv_dir}/bin:{os.environ.get('PATH', '')}",
        }

    @property
    def cmake_env(self) -> dict[str, str]:
        pfx = str(self.install_prefix)
        pkg_path = f"{pfx}/lib/pkgconfig:{pfx}/lib64/pkgconfig"
        return os.environ | {
            "CMAKE_PREFIX_PATH": pfx,
            "PKG_CONFIG_PATH": pkg_path,
            "PKG_CONFIG_LIBDIR": pkg_path,
            "PATH": f"{self.venv_dir}/bin:{os.environ.get('PATH', '')}",
        }
