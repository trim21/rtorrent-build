"""Build orchestrator for rtorrent-static."""

import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from graphlib import TopologicalSorter
from pathlib import Path

from . import PROJECT_ROOT
from ._types import Arch, Libc
from .cache import CacheStore, compute_merkle_hash
from .deps.boost import BoostBuilder
from .deps.brotli import BrotliBuilder
from .deps.cares import CaresBuilder
from .deps.curl import CurlBuilder
from .deps.libidn2 import Libidn2Builder
from .deps.libtorrent import LibtorrentBuilder
from .deps.libtorrent_rasterbar import LibtorrentRasterbarBuilder
from .deps.libunistring import LibunistringBuilder
from .deps.lua import LuaBuilder
from .deps.luajit import LuaJITBuilder
from .deps.ncurses import NcursesBuilder
from .deps.nghttp2 import Nghttp2Builder
from .deps.openssl import OpensslBuilder
from .deps.qbittorrent import QbittorrentBuilder
from .deps.qt import QtBuilder
from .deps.qttools import QtToolsBuilder
from .deps.rtorrent import RtorrentBuilder
from .deps.zlib import ZlibBuilder
from .deps.zstd import ZstdBuilder
from .manifest import ResolvedManifest, deps_for, reachable_packages
from .toolchain import Builder, ResolvedSource, Toolchain

_BUILDER_MAP: dict[str, type[Builder]] = {
    "zlib": ZlibBuilder,
    "openssl": OpensslBuilder,
    "brotli": BrotliBuilder,
    "cares": CaresBuilder,
    "ncurses": NcursesBuilder,
    "curl": CurlBuilder,
    "lua": LuaBuilder,
    "luajit": LuaJITBuilder,
    "nghttp2": Nghttp2Builder,
    "libunistring": LibunistringBuilder,
    "libidn2": Libidn2Builder,
    "rtorrent-libtorrent": LibtorrentBuilder,
    "boost": BoostBuilder,
    "libtorrent-rasterbar": LibtorrentRasterbarBuilder,
    "zstd": ZstdBuilder,
    "qt": QtBuilder,
    "qttools": QtToolsBuilder,
    "qbittorrent": QbittorrentBuilder,
    "rtorrent": RtorrentBuilder,
}

_ALLOWED_SOS = frozenset(
    {
        "ld-linux-x86-64.so.2",
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
    gen_end: float = 0.0
    end: float = 0.0
    skipped: bool = False


def _fmt_ts(sec: float) -> str:
    if sec < 60:
        return f"{sec:.1f}s"
    return f"{int(sec // 60)}m{sec % 60:.0f}s"


def _render_timeline_table(timings: list[_Timing], total_elapsed: float) -> None:
    if not timings:
        return
    wall = _fmt_ts(total_elapsed)

    names = [t.name for t in timings]
    name_w = max(max(len(n) for n in names), 8)

    gens: list[str] = []
    builds: list[str] = []
    totals: list[str] = []
    for t in timings:
        if t.skipped:
            gens.append("skipped")
            builds.append("skipped")
            totals.append("skipped")
        else:
            gens.append(_fmt_ts(t.gen_end - t.start))
            builds.append(_fmt_ts(t.end - t.gen_end))
            totals.append(_fmt_ts(t.end - t.start))

    header = f"| {'':<{name_w}} | " + " | ".join(f"{n:^{name_w}}" for n in names) + " |"
    sep = "|-" + "-" * name_w + "-|" + "|".join("-" * (name_w + 2) for _ in names) + "|"
    gen_row = f"| {'Generate':<{name_w}} | " + " | ".join(f"{g:>{name_w}}" for g in gens) + " |"
    build_row = f"| {'Build':<{name_w}} | " + " | ".join(f"{b:>{name_w}}" for b in builds) + " |"
    total_row = f"| {'Total':<{name_w}} | " + " | ".join(f"{t:>{name_w}}" for t in totals) + " |"

    lines = [
        f"Build Timeline ({wall} wall)",
        header,
        sep,
        gen_row,
        build_row,
        total_row,
        "",
    ]
    out = "\n".join(lines)

    sys.stderr.write(out)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(out)


def _list_prefix_files(prefix: Path) -> set[Path]:
    if not prefix.exists():
        return set()
    return {p.relative_to(prefix) for p in prefix.rglob("*") if p.is_file()}


def build_rtorrent(
    *,
    variant: str,
    manifest: ResolvedManifest,
    work_dir: Path,
    output_dir: Path,
    skip_deps: list[str] | None = None,
    clean: bool = True,
    no_cache: bool = False,
    options: dict[str, str] | None = None,
    libc: Libc = Libc.glibc,
    arch: Arch = Arch.v1,
    docker_target_glibc: str | None = None,
    debug: bool = False,
    cache_dir: Path | None = None,
    jobs: int = 1,
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
        debug=debug,
    )
    tc.setup()

    pkgs = manifest.packages
    needed = reachable_packages(pkgs, manifest.executable_package)
    names = [n for n in _BUILDER_MAP if n in needed]

    ts = TopologicalSorter({name: [d for d in deps_for(name, pkgs) if d in pkgs] for name in names})
    ts.prepare()

    resolved: dict[str, ResolvedSource] = {}
    timings: list[_Timing] = []
    build_origin = time.monotonic()
    _pkg_hashes: dict[str, str] = {}
    _cache_store = CacheStore(cache_dir) if cache_dir else None

    def _build_pkg(name: str) -> str:
        t = _Timing(name=name, start=time.monotonic() - build_origin)
        timings.append(t)

        pkg = pkgs[name]
        lib = pkg.to_libinfo()
        builder_cls = _BUILDER_MAP[name]
        commander = tc.make_commander(name)

        source = tc.prepare_source(name, lib)
        resolved[name] = source
        builder = builder_cls(tc, lib, source, commander)
        features = builder.cache_key_extra

        dep_hashes = {d: _pkg_hashes[d] for d in deps_for(name, pkgs) if d in _pkg_hashes}
        merkle_hash = compute_merkle_hash(
            name=name,
            version=source.version,
            url=pkg.url,
            options=features,
            toolchain_name=tc._toolchain_name,
            zig_version=tc.zig_version,
            libc=tc.libc.value,
            arch=tc.arch.safe,
            glibc_target=tc._glibc_target,
            debug=tc.debug,
            install_prefix=str(tc.install_prefix.resolve()),
            dep_hashes=dep_hashes,
        )
        _pkg_hashes[name] = merkle_hash

        if not no_cache and tc.is_built_merkle(name, merkle_hash):
            print(f"Already built {name} {source.version}")
            t.gen_end = time.monotonic() - build_origin
            t.end = time.monotonic() - build_origin
            return name

        if _cache_store and _cache_store.has(merkle_hash):
            print(f"Persistent cache hit for {name}")
            _cache_store.restore(merkle_hash, tc.install_prefix, name)
            tc.mark_built_merkle(name, merkle_hash)
            t.gen_end = time.monotonic() - build_origin
            t.end = time.monotonic() - build_origin
            return name

        before_files = _list_prefix_files(tc.install_prefix)

        tc.clean_source(name, lib)
        source = tc.prepare_source(name, lib)
        resolved[name] = source
        builder = builder_cls(tc, lib, source, commander)
        t.gen_end = time.monotonic() - build_origin
        builder.build()
        tc.mark_built_merkle(name, merkle_hash)
        t.end = time.monotonic() - build_origin

        if _cache_store:
            after_files = _list_prefix_files(tc.install_prefix)
            new_files = after_files - before_files
            if new_files:
                _cache_store.store_files(merkle_hash, tc.install_prefix, new_files, name)

        return name

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures: dict[concurrent.futures.Future[str], str] = {}

        while ts.is_active() or futures:
            ready_names = ts.get_ready()
            for name in ready_names:
                if name in skip_deps:
                    print(f"Skipping {name}")
                    timings.append(_Timing(name=name, start=0, end=0, skipped=True))
                    ts.done(name)

            unblocked = [n for n in ready_names if n not in skip_deps]
            for n in unblocked:
                futures[pool.submit(_build_pkg, n)] = n

            if not futures:
                break

            done_set, _ = concurrent.futures.wait(
                futures, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in done_set:
                name = futures.pop(future)
                future.result()
                ts.done(name)

    total_elapsed = time.monotonic() - build_origin
    if _cache_store:
        _cache_store.gc(set(_pkg_hashes.values()))
    _render_timeline_table(timings, total_elapsed)

    app_name = manifest.executable_package
    top_source = resolved[app_name]
    binary = _binary_path(tc, app_name)

    if app_name == "qbittorrent" and "libtorrent-rasterbar" in resolved:
        lt_version = resolved["libtorrent-rasterbar"].version
        short_name = "qb"
        version_tag = f"{top_source.version}-lt-{lt_version}"
    else:
        short_name = app_name
        version_tag = top_source.version

    if libc == Libc.musl:
        output_name = f"{short_name}-{version_tag}.{arch.safe}-musl"
    else:
        output_name = f"{short_name}-{version_tag}.{arch.safe}.glibc.{glibc_target}"
    output_bin = output_dir / output_name
    if not binary.exists():
        raise FileNotFoundError(f"Binary not found: {binary}")
    _verify_linkage(binary)
    shutil.copy2(str(binary), str(output_bin))
    output_bin.chmod(0o755)
    print(f"Copied {binary} -> {output_bin}")

    print(f"Build complete for {variant}")
    return output_bin
