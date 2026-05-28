"""Generate manifest.schema.json from the pydantic RawManifest model."""

import json
from pathlib import Path

from rtorrent_builder.manifest import _raw_manifest_adapter

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "manifest.schema.json"


def generate() -> None:
    schema = _raw_manifest_adapter.json_schema()

    props: dict = schema.setdefault("properties", {})
    props["$schema"] = {"type": "string", "description": "JSON Schema reference"}

    schema.pop("title", None)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://rtorrent-static/manifest.schema.json"
    schema["title"] = "Build Manifest"
    schema["description"] = "Build manifest for rtorrent-static variants"

    SCHEMA_PATH.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
    print(f"Schema written to {SCHEMA_PATH}")


if __name__ == "__main__":
    generate()
