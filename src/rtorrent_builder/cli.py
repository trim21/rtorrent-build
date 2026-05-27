"""CLI entry point for rtorrent-static builder."""

import json
import re
import subprocess
from enum import Enum
from pathlib import Path

import click

from . import PROJECT_ROOT
from ._types import Arch, Libc
from .builder import _BUILDER_MAP, _FINAL_PACKAGES, build_rtorrent
from .docker import DISTROLESS_GLIBC_VERSION, build_docker_image
from .manifest import load_manifest


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


def _dep_choices() -> list[str]:
    return sorted(name for name in _BUILDER_MAP if name not in _FINAL_PACKAGES)


@click.command()
@click.argument("variant", nargs=1, type=click.Choice(_variant_choices()))
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
    "--skip-deps",
    multiple=True,
    type=click.Choice(_dep_choices()),
    help="Skip building specific dependencies (must already be installed)",
)
@click.option(
    "--clean",
    is_flag=True,
    help="Clean build directory before starting",
)
@click.option(
    "--no-cache",
    is_flag=True,
    default=False,
    help="Disable build cache — rebuild all packages",
)
@click.option(
    "--disguise",
    is_flag=True,
    default=False,
    help="Disguise as rtorrent/0.9.8/0.13.8",
)
@click.option(
    "--libc",
    type=click.Choice([e.value for e in CliLibc]),
    default=CliLibc.glibc.value,
    show_default=True,
    help="Target libc: glibc (dynamic), musl (fully static), current (host glibc)",
)
@click.option(
    "--arch",
    type=click.Choice([e.value for e in Arch]),
    default=Arch.v1.value,
    show_default=True,
    help="x86-64 microarchitecture level (v1=baseline, v2=SSE4, v3=AVX2)",
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
def main(
    variant: str,
    work_dir: Path,
    output_dir: Path,
    skip_deps: tuple[str, ...],
    clean: bool,
    no_cache: bool,
    disguise: bool,
    libc: str,
    arch: str,
    build_docker: bool,
    build_info: Path | None,
) -> None:
    output_dir = output_dir.resolve()

    variant_work = (work_dir / variant).resolve()
    print(f"Starting rtorrent-static build for {variant}")
    print(f"Work directory: {variant_work}")

    manifest = load_manifest(variant)

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

    output_bin = build_rtorrent(
        variant=variant,
        manifest=manifest,
        work_dir=variant_work,
        output_dir=output_dir,
        skip_deps=list(skip_deps) if skip_deps else [],
        clean=clean,
        no_cache=no_cache,
        options=options,
        libc=resolved_libc,
        arch=Arch(arch),
        docker_target_glibc=glibc_override,
    )

    if build_docker:
        tag = _build_docker(output_bin, variant=variant, arch=arch, disguise=disguise)
        if build_info:
            info = {"tag": tag}
            build_info.parent.mkdir(parents=True, exist_ok=True)
            build_info.write_text(json.dumps(info, indent=2) + "\n")
            print(f"Build info written to {build_info}")

    print(f"Build complete for {variant}")


def _build_docker(binary_path: Path, *, variant: str, arch: str, disguise: bool) -> str:
    version = variant.removeprefix("rtorrent-")
    arch_safe = Arch(arch).safe
    suffix = "-disguised" if disguise else ""
    tag = f"{version}{suffix}.{arch_safe}"
    image_ref = f"rtorrent:{tag}"
    output_name = binary_path.stem
    print(f"Building Docker image: {image_ref}")
    build_docker_image(binary_path, output_name, image_ref)
    return tag


if __name__ == "__main__":
    main()  # pyright: ignore[reportCallIssue] — Click handles argument parsing
