"""Docker image builder using GCP distroless or debian-slim base."""

import subprocess
from pathlib import Path

from jinja2 import BaseLoader, Environment

DISTROLESS_BASE = "gcr.io/distroless/cc-debian13"
DISTROLESS_GLIBC_VERSION = "2.40"
DEBUG_BASE = "debian:bookworm-slim"

_TEMPLATE_PATH = Path(__file__).parent / "dockerfile.j2"
_TEMPLATE = Environment(loader=BaseLoader()).from_string(_TEMPLATE_PATH.read_text())


def build_docker_image(
    binary_path: Path,
    output_name: str,
    image_tag: str,
    *,
    debug: bool = False,
    labels: dict[str, str] | None = None,
) -> None:
    """Build a distroless (or debian-slim+gdb for debug) Docker image."""
    base_image = DEBUG_BASE if debug else DISTROLESS_BASE
    dockerfile = binary_path.parent / f"Dockerfile.{output_name}"
    try:
        dockerfile.write_text(
            _TEMPLATE.render(
                base_image=base_image,
                binary=binary_path.name,
                debug=debug,
                labels=labels or {},
            )
        )
        build_context = binary_path.parent
        cmd = [
            "docker",
            "build",
            "-t",
            image_tag,
            "-f",
            str(dockerfile),
            str(build_context),
        ]
        print(f"$ {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        print(f"Built Docker image: {image_tag}")
    finally:
        if dockerfile.exists():
            dockerfile.unlink()
