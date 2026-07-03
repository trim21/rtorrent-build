"""Generate release notes from manifest and lock files.

Usage:
    uv run python scripts/generate_release_notes.py <manifest...> [--output FILE]
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import click
from jinja2 import Environment, FileSystemLoader

from rtorrent_builder.lock import load_resolved_manifest
from rtorrent_builder.manifest import (
    _load_jsonc_text,
    _raw_manifest_adapter,
    _resolve_extends,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFESTS_DIR = PROJECT_ROOT / "manifests"
_TEMPLATE_DIR = Path(__file__).resolve().parent


# ────────────────────────────────────────── data ──────────────────────────────────────────


@dataclass
class PkgInfo:
    name: str
    version: str


@dataclass
class VariantInfo:
    name: str
    executable: str
    app_version: str
    target_glibc: str
    packages: list[PkgInfo] = field(default_factory=list)


# ──────────────────────────────────────── collection ───────────────────────────────────────


def load_variant(manifest_path: Path) -> VariantInfo | None:
    stem = manifest_path.stem
    if stem == "common":
        return None
    if not manifest_path.with_suffix(".lock").exists():
        return None

    raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
    raw = _resolve_extends(raw, MANIFESTS_DIR)

    resolved = load_resolved_manifest(manifest_path)
    executable = resolved.executable_package
    app_pkg = resolved.packages.get(executable)
    app_version = app_pkg.version if app_pkg else ""

    packages = sorted(
        (PkgInfo(name, p.version) for name, p in resolved.packages.items() if p.version),
        key=lambda p: p.name,
    )

    return VariantInfo(
        name=stem,
        executable=executable,
        app_version=app_version,
        target_glibc=resolved.target_glibc,
        packages=packages,
    )


# ──────────────────────────────────────── template ─────────────────────────────────────────

_TEMPLATE_ENV = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
_RELEASE_TEMPLATE = _TEMPLATE_ENV.get_template("RELEASE.md.j2")


# ───────────────────────────────────────────── CLI ─────────────────────────────────────────


@click.command()
@click.argument(
    "manifest",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
@click.option(
    "--output",
    "output_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Write combined release notes to file (default: stdout)",
)
def main(manifest: tuple[Path, ...], output_file: Path | None) -> None:
    """Generate release notes for one or more manifest variants."""
    parts: list[str] = []
    for m in manifest:
        v = load_variant(m)
        if v is None:
            click.echo(f"Skipping {m.stem}: no lock file", err=True)
            continue
        parts.append(_RELEASE_TEMPLATE.render(variant=v).strip())

    if not parts:
        click.echo("No variants found", err=True)
        sys.exit(1)

    body = ("\n\n---\n\n".join(parts) if len(parts) > 1 else parts[0]) + "\n"

    if output_file:
        output_file.write_text(body)
        click.echo(f"Wrote {output_file}")
    else:
        click.echo(body)


if __name__ == "__main__":
    main()
