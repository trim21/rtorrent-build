"""Build orchestrator for rtorrent-static."""

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from graphlib import TopologicalSorter
from pathlib import Path

from . import PROJECT_ROOT
from ._types import Arch, Libc
from .deps.boost import BoostBuilder
from .deps.brotli import BrotliBuilder
from .deps.cares import CaresBuilder
from .deps.curl import CurlBuilder
from .deps.libtorrent import LibtorrentBuilder
from .deps.libtorrent_rasterbar import LibtorrentRasterbarBuilder
from .deps.lua import LuaBuilder
from .deps.ncurses import NcursesBuilder
from .deps.openssl import OpensslBuilder
from .deps.qbittorrent import QbittorrentBuilder
from .deps.qt import QtBuilder
from .deps.qttools import QtToolsBuilder
from .deps.rtorrent import RtorrentBuilder
from .deps.zlib import ZlibBuilder
from .deps.zstd import ZstdBuilder
from .manifest import Manifest
from .toolchain import Builder, ResolvedSource, Toolchain

_BUILDER_MAP: dict[str, type[Builder]] = {
    "zlib": ZlibBuilder,
    "openssl": OpensslBuilder,
    "brotli": BrotliBuilder,
    "cares": CaresBuilder,
    "ncurses": NcursesBuilder,
    "curl": CurlBuilder,
    "lua": LuaBuilder,
    "rtorrent-libtorrent": LibtorrentBuilder,
    "boost": BoostBuilder,
    "libtorrent-rasterbar": LibtorrentRasterbarBuilder,
    "zstd": ZstdBuilder,
    "qt": QtBuilder,
    "qttools": QtToolsBuilder,
    "qbittorrent": QbittorrentBuilder,
    "rtorrent": RtorrentBuilder,
}

_FINAL_PACKAGES: set[str] = {"rtorrent", "qbittorrent"}

_DEPENDENCIES: dict[str, list[str]] = {
    "zlib": [],
    "openssl": [],
    "brotli": [],
    "cares": [],
    "ncurses": [],
    "lua": [],
    "curl": ["zlib", "openssl", "brotli", "cares", "zstd"],
    "rtorrent-libtorrent": ["openssl", "curl", "zlib"],
    "boost": [],
    "libtorrent-rasterbar": ["boost", "openssl"],
    "zstd": [],
    "qt": ["zlib", "openssl", "zstd", "brotli"],
    "qttools": ["qt"],
    "qbittorrent": [
        "zlib",
        "openssl",
        "boost",
        "libtorrent-rasterbar",
        "qt",
        "qttools",
    ],
    "rtorrent": [
        "zlib",
        "openssl",
        "brotli",
        "cares",
        "ncurses",
        "curl",
        "rtorrent-libtorrent",
        "lua",
    ],
}


def _reachable_packages(pkgs: dict) -> set[str]:
    top = _top_package(pkgs)
    reachable: set[str] = set()
    stack = [top]
    while stack:
        name = stack.pop()
        if name in reachable:
            continue
        reachable.add(name)
        for dep in _DEPENDENCIES.get(name, []):
            if dep in pkgs and dep not in reachable:
                stack.append(dep)
    return reachable


def _top_package(pkgs: dict) -> str:
    dependents: set[str] = set()
    for name in pkgs:
        for dep in _DEPENDENCIES.get(name, []):
            if dep in pkgs:
                dependents.add(dep)
    candidates = [n for n in pkgs if n not in dependents]
    finals = [n for n in candidates if n in _FINAL_PACKAGES]
    if len(finals) != 1:
        raise ValueError(f"Expected exactly one top-level final package, got: {finals}")
    return finals[0]


_ALLOWED_SOS = frozenset(
    {
        "libc.so.6",
        "libm.so.6",
        "libdl.so.2",
        "libpthread.so.0",
        "librt.so.1",
        "libresolv.so.2",
        "libnsl.so.1",
        "libutil.so.1",
    }
)


def _verify_linkage(binary: Path) -> None:
    try:
        result = subprocess.run(
            ["readelf", "-d", str(binary)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("WARNING: readelf not found, skipping linkage check")
        return

    if result.returncode != 0:
        print("WARNING: readelf failed, skipping linkage check")
        return

    linked = set()
    for line in result.stdout.splitlines():
        m = re.search(r"\(NEEDED\)\s+Shared library: \[(.+?)\]", line)
        if m:
            linked.add(m.group(1))

    if not linked:
        print("Linkage check: binary is fully static (no NEEDED entries)")
        return

    unexpected = linked - _ALLOWED_SOS
    if unexpected:
        print(f"ERROR: binary links to unexpected shared libraries: {sorted(unexpected)}")
        print("readelf -d NEEDED entries:\n" + "\n".join(f"  {s}" for s in sorted(linked)))
        raise SystemExit(1)

    print(f"Linkage check passed: {sorted(linked)}")


def _binary_path(tc: Toolchain, name: str) -> Path:
    if name == "rtorrent":
        return tc.install_prefix / "bin" / "rtorrent"
    if name == "qbittorrent":
        return tc.install_prefix / "bin" / "qbittorrent-nox"
    raise KeyError(f"No binary path known for top-level package: {name}")


@dataclass
class _Timing:
    name: str
    start: float
    end: float = 0.0
    skipped: bool = False


def _render_timeline(timings: list[_Timing], total_elapsed: float) -> None:
    if not timings:
        return

    timings.sort(key=lambda t: t.start)
    active = [t for t in timings if not t.skipped]
    if not active:
        return

    origin = min(t.start for t in active)
    wall = total_elapsed

    bar_width = 50
    name_w = max(len(t.name) for t in timings) + 1

    def _fmt_ts(sec: float) -> str:
        if sec < 60:
            return f"{sec:.1f}s"
        return f"{int(sec // 60)}m{sec % 60:.0f}s"

    print()
    print(f"Build Timeline ({_fmt_ts(wall)} wall)")
    print("-" * (name_w + bar_width + 20))

    for t in timings:
        if t.skipped:
            print(f"{' ' * name_w} {'.' * bar_width}  skipped")
            continue

        s = t.start - origin
        e = t.end - origin
        scol = int(s / wall * bar_width)
        ecol = int(e / wall * bar_width)
        scol = max(0, min(scol, bar_width - 1))
        ecol = max(scol + 1, min(ecol, bar_width))

        bar = "." * scol + "#" * (ecol - scol) + "." * (bar_width - ecol)
        dur = _fmt_ts(t.end - t.start)
        print(f"{t.name:<{name_w}} {bar}  {dur}")

    print("-" * (name_w + bar_width + 20))
    print()

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"## Build Timeline ({_fmt_ts(wall)} wall)\n\n")
            f.write("| Package | Duration |\n")
            f.write("|---------|----------|\n")
            for t in timings:
                dur = "skipped" if t.skipped else _fmt_ts(t.end - t.start)
                f.write(f"| {t.name} | {dur} |\n")
            f.write("\n")


def build_rtorrent(
    *,
    variant: str,
    manifest: Manifest,
    work_dir: Path,
    output_dir: Path,
    skip_deps: list[str] | None = None,
    clean: bool = True,
    no_cache: bool = False,
    options: dict[str, str] | None = None,
    libc: Libc = Libc.glibc,
    arch: Arch = Arch.v1,
    docker_target_glibc: str | None = None,
) -> Path:
    skip_deps = skip_deps or []

    work_dir = work_dir.resolve()
    output_dir = output_dir.resolve()

    if clean and work_dir.exists():
        print(f"Cleaning work directory: {work_dir}")
        shutil.rmtree(work_dir)

    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    glibc_target = docker_target_glibc or manifest.target_glibc
    tc = Toolchain(
        variant=variant,
        toolchain=manifest.toolchain,
        work_dir=work_dir,
        project_root=PROJECT_ROOT,
        glibc_target=glibc_target,
        options=options,
        libc=libc,
        arch=arch,
    )
    tc.setup()

    pkgs = manifest.packages
    needed = _reachable_packages(pkgs)
    names = [n for n in _BUILDER_MAP if n in needed]

    ts = TopologicalSorter({name: [d for d in _DEPENDENCIES[name] if d in pkgs] for name in names})
    ts.prepare()

    resolved: dict[str, ResolvedSource] = {}
    timings: list[_Timing] = []
    build_origin = time.monotonic()

    def _build_pkg(name: str) -> str:
        t = _Timing(name=name, start=time.monotonic() - build_origin)
        timings.append(t)

        pkg = pkgs[name]
        builder_cls = _BUILDER_MAP[name]
        commander = tc.make_commander(name)

        source = tc.prepare_source(name, pkg)
        resolved[name] = source
        builder = builder_cls(tc, pkg, source, commander)
        features = builder.cache_key_extra

        if not no_cache and tc.is_built(name, source.version, features):
            print(f"Already built {name} {source.version}")
            t.end = time.monotonic() - build_origin
            return name

        tc.clean_source(name, pkg)
        source = tc.prepare_source(name, pkg)
        resolved[name] = source
        builder = builder_cls(tc, pkg, source, commander)
        builder.build()
        tc.mark_built(name, source.version, features)
        t.end = time.monotonic() - build_origin
        return name

    while ts.is_active():
        for name in ts.get_ready():
            if name in skip_deps:
                print(f"Skipping {name}")
                timings.append(_Timing(name=name, start=0, end=0, skipped=True))
                ts.done(name)
                continue
            _build_pkg(name)
            ts.done(name)

    total_elapsed = time.monotonic() - build_origin
    _render_timeline(timings, total_elapsed)

    app_name = _top_package(pkgs)
    top_source = resolved[app_name]
    binary = _binary_path(tc, app_name)

    if libc == Libc.musl:
        output_name = f"{app_name}-{top_source.version}.{arch.safe}-musl"
    else:
        output_name = f"{app_name}-{top_source.version}.{arch.safe}.glibc.{glibc_target}"
    output_bin = output_dir / output_name
    if not binary.exists():
        raise FileNotFoundError(f"Binary not found: {binary}")
    _verify_linkage(binary)
    shutil.copy2(str(binary), str(output_bin))
    output_bin.chmod(0o755)
    print(f"Copied {binary} -> {output_bin}")

    print(f"Build complete for {variant}")
    return output_bin
