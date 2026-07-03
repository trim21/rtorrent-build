# rtorrent-static

Build orchestrator that produces statically-linked rtorrent, qbittorrent, and transmission binaries using Zig as the C/C++ toolchain.

## Build & CI

```bash
# Build variants
python build.py build manifests/rtorrent-0.9.8.jsonc
python build.py build manifests/rtorrent-0.16.jsonc
python build.py build manifests/rtorrent-master.jsonc
python build.py build manifests/qbittorrent-5.2-lt2.jsonc
python build.py build manifests/transmission.jsonc

# With options
python build.py build manifests/rtorrent-master.jsonc --libc musl --arch amd/v2
python build.py build manifests/rtorrent-master.jsonc --disguise
python build.py build manifests/rtorrent-master.jsonc --libc current        # target host glibc version
python build.py build manifests/rtorrent-master.jsonc --docker               # build distroless Docker image
python build.py build manifests/rtorrent-master.jsonc --no-cache             # disable build cache
python build.py build manifests/rtorrent-master.jsonc --cache-dir /tmp/cache # persistent Merkle-tree build cache
python build.py build manifests/rtorrent-master.jsonc --cache-gc             # garbage collect build cache
python build.py build manifests/rtorrent-master.jsonc --jobs 4               # concurrent package builds
python build.py build manifests/rtorrent-master.jsonc --debug                # debug build
python build.py build manifests/rtorrent-master.jsonc --build-info           # write build metadata JSON
```

CI: `.github/workflows/build.yaml` — matrix of variants × 2 libc × 3 arch, triggered on push to master, tags (`v*`), PRs, and manual dispatch.

Additional workflows:
- `.github/workflows/manifest-lock.yaml` — daily uv.lock update + auto-PR for manifest lockfiles
- `.github/workflows/new-release.yml` — daily check for new rtorrent releases, auto-creates manifest PRs
- `.github/workflows/docker.yaml` — builds and pushes distroless Docker images to ghcr.io
- `.github/workflows/cleanup-runs.yaml` — cancels stale workflow runs on PR close

## Lint & Type Check

```bash
pre-commit run --all-files
ruff check src/
ruff format --check src/
pyright src/
```

- Ruff: rules E, F, I, N, W, UP, B, C4, SIM; line length 100; double quotes; LF line endings
- dprint (`dprint.json`): formats TOML, YAML, JSON, beancount, TypeScript
- Pyright: `typeCheckingMode = "basic"`, Python 3.12

No test suite exists. Validation is CI build success.

## Architecture

```
build.py                    → entry point, calls rtorrent_builder.cli:main
src/rtorrent_builder/       → Python package
  cli.py                    → Click CLI (manifest path, --libc, --arch, --docker, --disguise, etc.)
  builder.py                → orchestrator (topological sort, incremental builds, build timeline)
  toolchain.py              → Zig + CMake toolchain setup, Builder ABC
  manifest.py               → Pydantic manifest loader (JSONC, extends, lockfiles)
  download.py               → httpx download with tqdm + retry
  run.py                    → Commander subprocess wrapper (per-package logging, auto nproc)
  docker.py                 → distroless Docker image builder
  dockerfile.j2             → Jinja2 Dockerfile template
  cache.py                  → Merkle-tree persistent build cache
  lock.py                   → git resolution and lockfile generation
  version_range.py          → PEP 440 version range parser
  _types.py                 → Libc/Arch enums (Arch: x86_64, x86_64_v2, x86_64_v3, x86_64_v4, native)
  _options.py               → per-package build options (disguise)
  utils.py                  → replace_in_file helper
  deps/                     → dependency builders
    _cmake.py               → CMakeBuilder base class
    _make.py                → MakeBuilder base class (autotools)
    _meson.py               → MesonBuilder base class
    zlib.py, openssl.py, brotli.py, ncurses.py, curl.py,
    cares.py, zstd.py, boost.py, lua.py, luajit.py,
    libtorrent.py, libtorrent_rasterbar.py, libdeflate.py,
    libidn2.py, libunistring.py, nghttp2.py,
    qtbase.py, qttools.py, qbittorrent.py,
    rtorrent.py, rtorrent_meson.py, transmission.py
manifests/                  → JSONC manifests per variant (versions, URLs, extends)
  base/common.jsonc         → shared dependency versions (extended by other manifests)
  base/openssl3.jsonc       → extends common with openssl 3.x version constraint
  *.lock                    → git SHA lockfiles for git-sourced deps
toolchains/default/         → toolchain venv (ziglang + cmake)
scripts/
  lock.py                   → regenerate manifest lockfiles
  new-rtorrent-release.py   → detect new rtorrent releases
  generate_schema.py        → manifest JSON schema generation
  generate_readme.py        → generate README from Jinja2 template
  pr-body.py                → generate PR body for auto-lock PRs
```

Build flow: download tarball → extract → configure → make → install to shared `install_prefix`.
Each package gets a `Commander` instance that logs to `build/{variant}/logs/{name}.log`.
Completions tracked via `.markers/{name}-{version}-{features_hash}` for resume.
Build timeline table printed at the end (and written to `GITHUB_STEP_SUMMARY` in CI).
Linkage verification via `readelf -d` ensures only allowed `.so` deps (glibc family).
Final binary: `dist/{name}-{version}.{arch}.glibc.{glibc_version}` or `dist/{name}-{version}.{arch}-musl`.

### Compiler & Linker Flags

All dependencies and final binaries are built with:

- `-fPIC` — position-independent code
- `-O2` — optimize for speed (not size)
- `-g` — emit debug info (preserved in final binary)
- `-flto` — full link-time optimization (applied to both compile and link steps)
- `-w` — suppress all compiler warnings
- `-march={x86_64,x86_64_v2,x86_64_v3,x86_64_v4}` — per-arch microarchitecture targeting
- `-s` is **not** used — debug symbols are kept in the final binary

These flags are set in `toolchain.py` for both CMake (`CMAKE_C_FLAGS_INIT`, `CMAKE_CXX_FLAGS_INIT`, `CMAKE_EXE_LINKER_FLAGS_INIT`) and autotools (`CFLAGS`, `LDFLAGS`) builds.

### Manifest Format

Manifests are JSONC files with optional `extends` for inheritance. `base/common.jsonc` defines shared deps; variant manifests extend it and add app-specific packages. Git-sourced deps are pinned in `.lock` files. Manifest hash is validated on load.

## Conventions

- Python 3.12+ (`X | Y` union syntax, `from __future__ import annotations`)
- Naming: `UPPER_CASE` constants, `PascalCase` builders, `snake_case` functions
- Double quotes, spaces (not tabs), LF line endings
- No comments unless explaining non-obvious logic
- Package manager: uv (via `uv.lock`)
- Build backend: pdm-backend
- Entry point: `rtorrent-build` (via `pyproject.toml [project.scripts]`)
