"""CLI entry point for rtorrent-static builder."""

import json
import os
import re
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path

import click

from . import PROJECT_ROOT
from ._types import Arch, Libc
from .builder import build_rtorrent
from .docker import DISTROLESS_GLIBC_VERSION, build_docker_image
from .lock import load_resolved_manifest, resolve_manifest
from .manifest import (
    GenericRefSource,
    GitHubPrSource,
    GitHubRefSource,
    ResolvedManifest,
    _load_jsonc_text,
    _raw_manifest_adapter,
)
from .run import CmdError


class CliLibc(Enum):
    """Extended libc choices for CLI including 'current'."""

    glibc = Libc.glibc.value
    musl = Libc.musl.value
    current = "current"


_MANIFESTS_DIR = PROJECT_ROOT / "manifests"


def _detect_host_glibc() -> str:
    output = subprocess.check_output(["ldd", "--version"], text=True)
    match = re.search(r"(\d+\.\d+)", output)
    if not match:
        raise RuntimeError("Could not detect host glibc version from ldd output")
    return match.group(1)


def _variant_choices() -> list[str]:
    return sorted(p.stem for p in _MANIFESTS_DIR.glob("*.jsonc") if p.stem != "common")


@click.group()
def main() -> None:
    """Static rtorrent/qbittorrent binary builder."""


@main.command()
@click.argument("manifest", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--work-dir",
    type=click.Path(path_type=Path),
    default=Path("build"),
    show_default=True,
    help="Working directory for builds",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=Path("dist"),
    show_default=True,
    help="Output directory for binaries",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Disable build cache — rebuild all packages",
)
@click.option(
    "--cache-gc",
    is_flag=True,
    default=False,
    envvar="RTORRENT_CACHE_GC",
    help="Run cache garbage collection after build (removes stale entries)",
)
@click.option(
    "--disguise/--no-disguise",
    default=False,
    envvar="RTORRENT_BUILD_DISGUISE",
    help="Disguise as rtorrent/0.9.8/0.13.8",
)
@click.option(
    "--libc",
    type=click.Choice([e.value for e in CliLibc]),
    default=CliLibc.glibc.value,
    show_default=True,
    envvar="RTORRENT_BUILD_LIBC",
    help="Target libc: glibc (dynamic), musl (fully static), current (host glibc)",
)
@click.option(
    "--arch",
    type=click.Choice([e.value for e in Arch]),
    default=Arch.v1.value,
    show_default=True,
    envvar="RTORRENT_BUILD_ARCH",
    help="x86-64 microarchitecture level (v1=baseline, v2=SSE4, v3=AVX2, native=host CPU)",
)
@click.option(
    "--docker",
    "build_docker",
    is_flag=True,
    default=False,
    help="Build a distroless Docker image from the output binary",
)
@click.option(
    "--build-info",
    type=click.Path(path_type=Path),
    default=None,
    help="Write build metadata (docker tag, version, etc.) to a JSON file",
)
@click.option(
    "--debug/--no-debug",
    default=False,
    envvar="RTORRENT_BUILD_DEBUG",
    help="Debug build: -g -O0, no LTO, enable debug in rtorrent/libtorrent",
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=None,
    envvar="RTORRENT_CACHE_DIR",
    help="Persistent cache directory for build artifacts (Merkle-tree keyed)",
)
@click.option(
    "--jobs",
    "-j",
    "jobs",
    type=int,
    default=1,
    show_default=True,
    envvar="RTORRENT_BUILD_JOBS",
    help="Max concurrent package builds (1 = sequential)",
)
def build(
    manifest: tuple[Path, ...],
    work_dir: Path,
    output_dir: Path,
    no_cache: bool,
    cache_gc: bool,
    disguise: bool,
    libc: str,
    arch: str,
    build_docker: bool,
    build_info: Path | None,
    debug: bool,
    cache_dir: Path | None,
    jobs: int,
) -> None:
    """Build one or more variants from manifest files."""
    output_dir = output_dir.resolve()

    options: dict[str, str] = {}
    if disguise:
        options["rtorrent.disguise"] = "1"
        options["rtorrent-libtorrent.disguise"] = "1"

    libc_enum = CliLibc(libc)
    if libc_enum == CliLibc.current and build_docker:
        raise click.BadParameter("--libc current cannot be used with --docker")
    glibc_override: str | None = None
    if libc_enum == CliLibc.current:
        resolved_libc = Libc.glibc
        glibc_override = _detect_host_glibc()
        print(f"Detected host glibc version: {glibc_override}")
    else:
        resolved_libc = Libc(libc_enum.value)
        if build_docker:
            glibc_override = DISTROLESS_GLIBC_VERSION

    for manifest_path in manifest:
        variant = manifest_path.stem
        variant_work = work_dir.resolve()
        print(f"Starting rtorrent-static build for {variant}")
        print(f"Work directory: {variant_work}")

        resolved = load_resolved_manifest(manifest_path)

        try:
            output_bin = build_rtorrent(
                variant=variant,
                manifest=resolved,
                work_dir=variant_work,
                output_dir=output_dir,
                no_cache=no_cache,
                cache_gc=cache_gc,
                options=options,
                libc=resolved_libc,
                arch=Arch(arch),
                docker_target_glibc=glibc_override,
                debug=debug,
                cache_dir=cache_dir,
                jobs=jobs,
            )
        except CmdError as e:
            log_path = variant_work / "logs"
            if e.output:
                sys.stderr.write(e.output)
            raise SystemExit(
                f"\nBuild failed: {e.cmd[0] if e.cmd else '?'} exited with {e.returncode}\n"
                f"Full log: {log_path}"
            ) from None
        except Exception as e:
            log_path = variant_work / "logs"
            raise SystemExit(f"\nBuild failed: {e}\nFull log: {log_path}") from None

        if build_docker:
            tags = _build_docker(
                output_bin,
                variant=variant,
                arch=arch,
                disguise=disguise,
                debug=debug,
                resolved=resolved,
                manifest_path=manifest_path,
            )
            summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
            if summary_path:
                with open(summary_path, "a") as f:
                    f.write(f"\n## Docker Image ({variant})\n\n")
                    for t in tags:
                        f.write(f"- `rtorrent:{t}`\n")
                    f.write("\n")
            if build_info:
                info = {"tags": tags}
                build_info.parent.mkdir(parents=True, exist_ok=True)
                build_info.write_text(json.dumps(info, indent=2) + "\n")
                print(f"Build info written to {build_info}")

        print(f"Build complete for {variant}")


@main.command()
@click.argument("manifest", nargs=-1)
def lock(manifest: tuple[str, ...]) -> None:
    """Regenerate lock files.

    Accepts manifest paths like manifests/rtorrent-fork.jsonc.
    If no MANIFEST is given, regenerates all lock files.
    """
    if manifest:
        for m in manifest:
            resolve_manifest(Path(m))
    else:
        for p in sorted(_MANIFESTS_DIR.glob("*.jsonc")):
            resolve_manifest(p)


def _docker_version_tags(
    version: str, variant_name: str, arch_safe: str, *, is_ref: bool
) -> list[str]:
    """Generate version-based Docker tags."""
    if is_ref:
        return [f"{variant_name}.{arch_safe}", f"{variant_name}-{version}.{arch_safe}"]
    parts = version.split(".")
    prefixes: list[str] = []
    for i in range(1, len(parts) + 1):
        prefix = ".".join(parts[:i])
        if prefix not in prefixes:
            prefixes.append(prefix)
    return [f"{p}.{arch_safe}" for p in prefixes]


def _build_docker(
    binary_path: Path,
    *,
    variant: str,
    arch: str,
    disguise: bool,
    debug: bool,
    resolved: ResolvedManifest,
    manifest_path: Path,
) -> list[str]:
    variant_name = variant.removeprefix("rtorrent-")
    arch_safe = Arch(arch).safe
    suffix = ""
    if disguise:
        suffix += "-disguised"
    if debug:
        suffix += "-debug"
    pkg = resolved.packages[resolved.executable_package]
    assert pkg.version, f"executable package {resolved.executable_package!r} has no version"
    full_version = pkg.version
    raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
    exe_pkg = raw.packages[resolved.executable_package]
    is_ref = (
        isinstance(exe_pkg.source, (GitHubRefSource, GitHubPrSource, GenericRefSource))
        if exe_pkg
        else False
    )
    tags = _docker_version_tags(full_version, variant_name, arch_safe, is_ref=is_ref)
    if suffix:
        tags = [f"{t}{suffix}" for t in tags]
    # include variant-derived tag if not already present
    variant_tag = f"{variant_name}{suffix}.{arch_safe}"
    if variant_tag not in tags:
        tags.insert(0, variant_tag)
    tags.append(f"{variant_name}{suffix}.{arch_safe}.{int(time.time())}")
    primary = tags[0]
    image_ref = f"rtorrent:{primary}"
    output_name = binary_path.stem
    print(f"Building Docker image: {image_ref}")
    build_docker_image(binary_path, output_name, image_ref, debug=debug)
    for extra in tags[1:]:
        extra_ref = f"rtorrent:{extra}"
        print(f"Tagging: {extra_ref}")
        subprocess.run(["docker", "tag", image_ref, extra_ref], check=True)
    return tags


if __name__ == "__main__":
    main()
