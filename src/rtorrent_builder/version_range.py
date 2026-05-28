"""Version range parser and matcher using PEP 440 via packaging."""

from __future__ import annotations

from packaging.specifiers import SpecifierSet
from packaging.version import Version


def matches(version: str, spec: str) -> bool:
    """Check if *version* satisfies the PEP 440 *spec* (e.g. ``>=5.1,<5.3``)."""
    return Version(version) in SpecifierSet(spec)


def resolve_best(versions: list[str], spec: str) -> str:
    """Return the highest version from *versions* matching *spec*."""
    specifier = SpecifierSet(spec)
    candidates = [v for v in versions if Version(v) in specifier]
    if not candidates:
        raise ValueError(f"No version matching {spec!r} found in {versions!r}")
    return max(candidates, key=lambda v: Version(v))
