# rtorrent-static

Build orchestrator that produces statically-linked rtorrent and qbittorrent binaries using Zig as the C/C++ toolchain.

## Build & CI

```bash
# Build variants
python build.py rtorrent-0.9.8
python build.py rtorrent-0.16.12
python build.py rtorrent-master
python build.py qbittorrent-5.2.1-lt2

# With options
python build.py rtorrent-master --libc musl --arch amd/v2
python build.py rtorrent-master --disguise
python build.py rtorrent-master --libc current        # target host glibc version
python build.py rtorrent-master --docker               # build distroless Docker image
python build.py rtorrent-master --skip-deps openssl    # skip already-built deps
python build.py rtorrent-master --no-cache             # disable build cache
```

CI: `.github/workflows/build.yml` — matrix of variants × 2 libc × 3 arch, triggered on push to master, tags (`v*`), PRs, and manual dispatch.

Additional workflows:
- `.github/workflows/lock.yml` — daily auto-update of `uv.lock`
- `.github/workflows/new-release.yml` — daily check for new rtorrent releases, auto-creates manifest PRs

## Lint & Type Check

```bash
pre-commit run --all-files
ruff check src/
ruff format --check src/
pyright src/
```

- Ruff: rules E, F, I, N, W, UP, B, C4, SIM; line length 100; double quotes; LF line endings
- dprint (`dprint.json`): formats TOML, YAML, JSON
- Pyright: `typeCheckingMode = "basic"`, Python 3.12

No test suite exists. Validation is CI build success.

## Architecture

```
build.py                    → entry point, calls rtorrent_builder.cli:main
src/rtorrent_builder/       → Python package
  cli.py                    → Click CLI (variant, --libc, --arch, --docker, --disguise, etc.)
  builder.py                → orchestrator (topological sort, incremental builds, build timeline)
  toolchain.py              → Zig + CMake toolchain setup, Builder ABC
  manifest.py               → Pydantic manifest loader (JSONC, extends, lockfiles)
  download.py               → httpx download with tqdm + retry
  run.py                    → Commander subprocess wrapper (per-package logging, auto nproc)
  docker.py                 → distroless Docker image builder
  dockerfile.j2             → Jinja2 Dockerfile template
  _types.py                 → Libc/Arch enums
  _options.py               → per-package build options (disguise)
  utils.py                  → replace_in_file helper
  deps/                     → dependency builders
    _cmake.py               → CMakeBuilder base class
    _make.py                → MakeBuilder base class (autotools)
    zlib.py, openssl.py, brotli.py, ncurses.py, curl.py,
    cares.py, zstd.py, boost.py, lua.py, luajit.py,
    libtorrent.py, libtorrent_rasterbar.py,
    qt.py, qttools.py, qbittorrent.py, rtorrent.py
manifests/                  → JSONC manifests per variant (versions, URLs, extends)
  common.jsonc              → shared dependency versions (extended by other manifests)
  *.lock                    → git SHA lockfiles for git-sourced deps
toolchains/default/         → toolchain venv (ziglang + cmake)
scripts/
  lock.py                   → regenerate lockfiles
  new-rtorrent-release.py   → detect new rtorrent releases
  generate_schema.py        → manifest JSON schema generation
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
- `-Os` — optimize for size
- `-g` — emit debug info (preserved in final binary)
- `-flto` — full link-time optimization (applied to both compile and link steps)
- `-w` — suppress all compiler warnings
- `-march={x86_64,x86_64_v2,x86_64_v3}` — per-arch microarchitecture targeting
- `-s` is **not** used — debug symbols are kept in the final binary

These flags are set in `toolchain.py` for both CMake (`CMAKE_C_FLAGS_INIT`, `CMAKE_CXX_FLAGS_INIT`, `CMAKE_EXE_LINKER_FLAGS_INIT`) and autotools (`CFLAGS`, `LDFLAGS`) builds.

### Manifest Format

Manifests are JSONC files with optional `extends` for inheritance. `common.jsonc` defines shared deps; variant manifests extend it and add app-specific packages. Git-sourced deps are pinned in `.lock` files. Manifest hash is validated on load.

## Conventions

- Python 3.12+ (`X | Y` union syntax, `from __future__ import annotations`)
- Naming: `UPPER_CASE` constants, `PascalCase` builders, `snake_case` functions
- Double quotes, spaces (not tabs), LF line endings
- No comments unless explaining non-obvious logic
- Package manager: uv (via `uv.lock`)
- Build backend: pdm-backend
- Entry point: `rtorrent-build` (via `pyproject.toml [project.scripts]`)
