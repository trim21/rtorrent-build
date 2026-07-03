"""Generate README.md from manifest and lock files.

Usage:
    uv run python scripts/generate_readme.py generate [--write] [--check]
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click
import yaml
from jinja2 import Environment, FileSystemLoader

from rtorrent_builder.lock import load_resolved_manifest
from rtorrent_builder.manifest import (
    GenericRefSource,
    GitHubPrSource,
    GitHubRefSource,
    _load_jsonc_text,
    _raw_manifest_adapter,
    _resolve_extends,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFESTS_DIR = PROJECT_ROOT / "manifests"
DOCKER_YAML = PROJECT_ROOT / ".github" / "workflows" / "docker.yaml"
_TEMPLATE_DIR = Path(__file__).resolve().parent


# ──────────────────────────────────────── docker matrix ────────────────────────────────────


def _parse_docker_info() -> dict[str, list[str]]:
    data = yaml.safe_load(DOCKER_YAML.read_text())
    matrix = _matrix_of(data, "docker")
    if not matrix:
        return {}
    variants: list[str] = matrix.get("variant", [])
    arches: list[str] = [a["name"] for a in matrix.get("arch", []) if isinstance(a, dict)]
    return dict.fromkeys(variants, arches)


def _matrix_of(data: dict, job_name: str) -> dict | None:
    jobs = data.get("jobs", {})
    job = jobs.get(job_name, {})
    strategy = job.get("strategy", {})
    return strategy.get("matrix") if isinstance(strategy, dict) else None


_DOCKER_INFO = _parse_docker_info()
DOCKER_VARIANTS = set(_DOCKER_INFO)


# ────────────────────────────────────────── data ──────────────────────────────────────────


@dataclass
class VariantInfo:
    name: str
    executable: str
    app_version: str
    target_glibc: str
    is_git_ref: bool = False
    git_ref_name: str = ""

    @property
    def display_name(self) -> str:
        if self.executable == "rtorrent":
            base = self.name.removeprefix("rtorrent-")
            if self.is_git_ref and base == self.git_ref_name:
                return f"rtorrent {self.git_ref_name}"
            return f"rtorrent {base}"
        if self.executable == "qbittorrent":
            return f"qBittorrent {self.name.removeprefix('qbittorrent-')}"
        if self.executable == "transmission":
            return "Transmission"
        return self.name

    @property
    def display_version(self) -> str:
        v = self.app_version
        if len(v) >= 7 and all(c in "0123456789abcdef" for c in v.lower()):
            return f"`{v[:12]}` (git)"
        return v

    @property
    def docker_variant_name(self) -> str:
        if self.executable == "rtorrent":
            inner = self.name.removeprefix("rtorrent-")
            return self.git_ref_name if self.is_git_ref else inner
        return self.name

    def docker_arches(self) -> list[str]:
        return _DOCKER_INFO.get(self.name, [])

    def docker_tags(self, arch_safe: str = "amd.v1") -> list[str]:
        variant_name = self.docker_variant_name
        if self.is_git_ref:
            tags = [
                f"{variant_name}.{arch_safe}",
                f"{variant_name}-{self.app_version[:12]}.{arch_safe}",
            ]
        else:
            parts = self.app_version.split(".")
            prefixes: list[str] = []
            for i in range(1, len(parts) + 1):
                p = ".".join(parts[:i])
                if p not in prefixes:
                    prefixes.append(p)
            tags = [f"{p}.{arch_safe}" for p in prefixes]
        vt = f"{variant_name}.{arch_safe}"
        if vt not in tags:
            tags.insert(0, vt)
        return tags


@dataclass
class AppGroup:
    key: str
    label: str
    variants: list[VariantInfo]


APP_ORDER = ["rtorrent", "qbittorrent", "transmission"]
APP_LABELS = {"rtorrent": "rtorrent", "qbittorrent": "qBittorrent", "transmission": "Transmission"}


# ──────────────────────────────────────── collection ───────────────────────────────────────


def collect_variants() -> list[VariantInfo]:
    result: list[VariantInfo] = []
    for manifest_path in sorted(MANIFESTS_DIR.glob("*.jsonc")):
        stem = manifest_path.stem
        if stem == "common":
            continue
        if not manifest_path.with_suffix(".lock").exists():
            continue

        raw = _raw_manifest_adapter.validate_python(_load_jsonc_text(manifest_path.read_text()))
        raw = _resolve_extends(raw, MANIFESTS_DIR)

        resolved = load_resolved_manifest(manifest_path)
        executable = resolved.executable_package
        app_pkg = resolved.packages.get(executable)
        app_version = app_pkg.version if app_pkg else ""

        is_git_ref = False
        git_ref_name = ""
        exe_manifest = raw.packages.get(executable)
        if exe_manifest is not None and isinstance(
            exe_manifest.source, (GitHubRefSource, GitHubPrSource, GenericRefSource)
        ):
            is_git_ref = True
            git_ref_name = str(exe_manifest.source.ref)

        result.append(
            VariantInfo(
                name=stem,
                executable=executable,
                app_version=app_version,
                target_glibc=resolved.target_glibc,
                is_git_ref=is_git_ref,
                git_ref_name=git_ref_name,
            )
        )

    return result


def build_app_groups(variants: list[VariantInfo], *, docker_only: bool = False) -> list[AppGroup]:
    by_app: dict[str, list[VariantInfo]] = {}
    for v in variants:
        if docker_only and v.name not in DOCKER_VARIANTS:
            continue
        by_app.setdefault(v.executable, []).append(v)
    return [
        AppGroup(
            key=app,
            label=APP_LABELS.get(app, app),
            variants=sorted(by_app.get(app, []), key=lambda x: x.name),
        )
        for app in APP_ORDER
        if app in by_app
    ]


# ──────────────────────────────────────── template ─────────────────────────────────────────

_TEMPLATE_ENV = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
_README_TEMPLATE = _TEMPLATE_ENV.get_template("README.md.j2")


# ───────────────────────────────────────────── CLI ─────────────────────────────────────────


@click.command()
@click.option("--write", is_flag=True, help="Write README.md in project root")
def generate(*, write: bool) -> None:
    """Generate README.md from manifests and lock files."""
    variants = collect_variants()
    apps = build_app_groups(variants)
    docker_apps = build_app_groups(variants, docker_only=True)
    readme = (
        _README_TEMPLATE.render(variants=variants, apps=apps, docker_apps=docker_apps).strip()
        + "\n"
    )
    readme_path = PROJECT_ROOT / "README.md"

    if write:
        readme_path.write_text(readme)
        click.echo(f"Wrote {readme_path}")
        return

    click.echo(readme)


if __name__ == "__main__":
    generate()
