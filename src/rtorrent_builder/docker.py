"""Docker image builder using GCP distroless base."""

import subprocess
from pathlib import Path

from jinja2 import BaseLoader, Environment

DISTROLESS_BASE = "gcr.io/distroless/cc-debian13"
DISTROLESS_GLIBC_VERSION = "2.40"

_TEMPLATE_PATH = Path(__file__).parent / "dockerfile.j2"
_TEMPLATE = Environment(loader=BaseLoader()).from_string(_TEMPLATE_PATH.read_text())


def build_docker_image(
    binary_path: Path,
    output_name: str,
    image_tag: str,
) -> None:
    """Build a distroless Docker image from a static rtorrent binary."""
    dockerfile = binary_path.parent / f"Dockerfile.{output_name}"
    try:
        dockerfile.write_text(
            _TEMPLATE.render(
                base_image=DISTROLESS_BASE,
                binary=binary_path.name,
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
