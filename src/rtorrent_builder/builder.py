"""Build orchestrator for rtorrent-static."""

import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import IntEnum
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


def _fix_shared_rpaths(tc: Toolchain, binary: Path) -> None:
    for d in (tc.install_prefix / "lib", tc.install_prefix / "lib64"):
        if not d.exists():
            continue
        for so in sorted(p for p in d.glob("*.so*") if p.is_file()):
            subprocess.run(
                [tc.patchelf_bin, "--set-rpath", "$ORIGIN", str(so)],
                check=True,
                capture_output=True,
            )

    subprocess.run(
        [tc.patchelf_bin, "--set-rpath", "$ORIGIN/rtorrent.libs", str(binary)],
        check=True,
        capture_output=True,
    )
    print("Fixed RPATH on shared libraries and binary")


def _copy_shared_libs(tc: Toolchain, dest_dir: Path, libs_name: str) -> None:
    libs_dir = dest_dir / libs_name
    libs_dir.mkdir(parents=True, exist_ok=True)
    for d in (tc.install_prefix / "lib", tc.install_prefix / "lib64"):
        if not d.exists():
            continue
        for so in d.glob("*.so*"):
            if so.is_file():
                shutil.copy2(str(so), str(libs_dir / so.name))
    print(f"Copied shared libraries to {libs_dir}")


def _verify_linkage(
    binary: Path, *, shared_deps: bool = False, install_prefix: Path | None = None
) -> None:
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

    if shared_deps and install_prefix is not None:
        built_sos: set[str] = set()
        for d in (install_prefix / "lib", install_prefix / "lib64"):
            if d.exists():
                for f in d.iterdir():
                    if f.is_file() and ".so" in f.name:
                        built_sos.add(f.name)
        unexpected = linked - _ALLOWED_SOS - built_sos
        if unexpected:
            print(
                f"ERROR: binary links to unexpected system shared libraries: {sorted(unexpected)}"
            )
            print(
                "Expected built SOs in prefix:\n  " + "\n  ".join(sorted(built_sos))
                if built_sos
                else "  (none found)"
            )
            print("readelf -d NEEDED entries:\n" + "\n".join(f"  {s}" for s in sorted(linked)))
            raise SystemExit(1)
        print(
            f"Linkage check (shared-deps): {len(linked)} NEEDED ("
            f"{len(linked & _ALLOWED_SOS)} system, {len(linked & built_sos)} built)"
        )
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


class _BuildSource(IntEnum):
    built = 0
    marker = 1
    cached = 2


@dataclass
class _Timing:
    name: str
    start: float
    gen_end: float = 0.0
    end: float = 0.0
    source: _BuildSource = _BuildSource.built


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
    statuses: list[str] = []
    for t in timings:
        if t.source == _BuildSource.cached:
            gens.append("-")
            builds.append("-")
            totals.append("-")
            statuses.append("cached")
        elif t.source == _BuildSource.marker:
            gens.append("-")
            builds.append("-")
            totals.append("-")
            statuses.append("marker")
        else:
            gens.append(_fmt_ts(t.gen_end - t.start))
            builds.append(_fmt_ts(t.end - t.gen_end))
            totals.append(_fmt_ts(t.end - t.start))
            statuses.append("built")

    header = f"| {'':<{name_w}} | " + " | ".join(f"{n:^{name_w}}" for n in names) + " |"
    sep = "|-" + "-" * name_w + "-|" + "|".join("-" * (name_w + 2) for _ in names) + "|"
    gen_row = f"| {'Generate':<{name_w}} | " + " | ".join(f"{g:>{name_w}}" for g in gens) + " |"
    build_row = f"| {'Build':<{name_w}} | " + " | ".join(f"{b:>{name_w}}" for b in builds) + " |"
    total_row = f"| {'Total':<{name_w}} | " + " | ".join(f"{t:>{name_w}}" for t in totals) + " |"
    status_row = (
        f"| {'Status':<{name_w}} | " + " | ".join(f"{s:^{name_w}}" for s in statuses) + " |"
    )

    lines = [
        f"Build Timeline ({wall} wall)",
        header,
        sep,
        gen_row,
        build_row,
        total_row,
        status_row,
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
    clean: bool = True,
    no_cache: bool = False,
    options: dict[str, str] | None = None,
    libc: Libc = Libc.glibc,
    arch: Arch = Arch.v1,
    docker_target_glibc: str | None = None,
    debug: bool = False,
    shared_deps: bool = False,
    cache_dir: Path | None = None,
    jobs: int = 1,
) -> Path:
    work_dir = work_dir.resolve()
    output_dir = output_dir.resolve()

    _variant_id = f"{variant}.debug" if debug else variant
    _variant_marker = work_dir / ".variant"

    if work_dir.exists():
        if clean:
            print(f"Cleaning work directory: {work_dir}")
            shutil.rmtree(work_dir)
        elif _variant_marker.exists():
            stored_variant = _variant_marker.read_text()
            if stored_variant != _variant_id:
                print(
                    f"Variant changed from {stored_variant!r} to {_variant_id!r}, "
                    f"cleaning work directory..."
                )
                shutil.rmtree(work_dir)
        else:
            print("Work directory exists without variant marker, cleaning...")
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
        shared_deps=shared_deps,
    )
    tc.setup()

    # Write variant marker after Toolchain init (which may have cleaned work_dir)
    _variant_marker.write_text(_variant_id)

    pkgs = manifest.packages
    needed = reachable_packages(pkgs, manifest.executable_package)
    missing = {n for n in needed if n in _BUILDER_MAP and n not in pkgs}
    if missing:
        msg = "WARNING: packages referenced as deps but not defined in manifest"
        print(f"{msg}: {missing}")
    names = [n for n in _BUILDER_MAP if n in needed and n in pkgs]

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
        cache_key = builder.cache_key_extra()

        dep_hashes = {d: _pkg_hashes[d] for d in deps_for(name, pkgs) if d in _pkg_hashes}
        merkle_hash, merkle_payload = compute_merkle_hash(
            name=name,
            version=source.version,
            url=pkg.url,
            options=cache_key,
            toolchain_name=tc._toolchain_name,
            zig_version=tc.zig_version,
            libc=tc.libc.value,
            arch=tc.arch.safe,
            glibc_target=tc._glibc_target,
            debug=tc.debug,
            shared_deps=tc.shared_deps,
            install_prefix=str(tc.install_prefix.resolve()),
            dep_hashes=dep_hashes,
        )
        _pkg_hashes[name] = merkle_hash

        if not no_cache and tc.is_built_merkle(name, merkle_hash):
            print(f"Already built {name} {source.version}")
            t.gen_end = time.monotonic() - build_origin
            t.end = time.monotonic() - build_origin
            t.source = _BuildSource.marker
            return name

        if _cache_store and _cache_store.has(name, merkle_hash):
            _cache_store.restore(name, merkle_hash, tc.install_prefix)
            tc.mark_built_merkle(name, merkle_hash)
            t.gen_end = time.monotonic() - build_origin
            t.end = time.monotonic() - build_origin
            t.source = _BuildSource.cached
            return name

        if _cache_store:
            _cache_store.diagnose_miss(name, merkle_payload)

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
                _cache_store.store_files(
                    name, merkle_hash, merkle_payload, tc.install_prefix, new_files
                )

        return name

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures: dict[concurrent.futures.Future[str], str] = {}

        while ts.is_active() or futures:
            ready_names = ts.get_ready()
            for n in ready_names:
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
        _cache_store.gc(_pkg_hashes)
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
    _verify_linkage(binary, shared_deps=shared_deps, install_prefix=tc.install_prefix)
    if shared_deps:
        _fix_shared_rpaths(tc, binary)
        _copy_shared_libs(tc, output_dir, "rtorrent.libs")
    shutil.copy2(str(binary), str(output_bin))
    output_bin.chmod(0o755)
    print(f"Copied {binary} -> {output_bin}")

    print(f"Build complete for {variant}")
    return output_bin
