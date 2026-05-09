# rtorrent-static

Build orchestrator that produces statically-linked rtorrent binaries using Zig as the C/C++ toolchain.

## Build & CI

```bash
# Build variants
python build.py rtorrent-0.9.8
python build.py rtorrent-0.16.11
python build.py rtorrent-master

# With options
python build.py rtorrent-master --libc musl --arch amd/v2
python build.py rtorrent-master --disguise
```

CI: `.github/workflows/build.yml` — matrix of 3 variants × 2 libc × 3 arch = 18 builds, triggered on push to master, tags (`v*`), PRs, and manual dispatch.

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
  cli.py                    → Click CLI
  builder.py                → orchestrator (topological sort, incremental builds)
  toolchain.py              → Zig + CMake toolchain setup
  manifest.py               → Pydantic manifest loader
  download.py               → httpx download with tqdm + retry
  run.py                    → subprocess wrapper
  rtorrent.py               → rtorrent builder (autotools: ./configure + make)
  deps/                     → dependency builders
    zlib.py, openssl.py, brotli.py, ncurses.py, curl.py,
    libtorrent.py, lua.py, luajit.py
manifests/                  → JSON manifests per variant (versions, URLs)
rtorrent-{variant}/         → per-variant toolchain venv (ziglang + cmake)
```

Build flow: download tarball → extract → configure → make → install to shared `install_prefix`.
Completions tracked via `.markers/{name}-{version}-{libc}-{arch}` for resume.
Final binary: `dist/rtorrent-{version}-{libc}-{arch}`.

### Compiler & Linker Flags

All dependencies and rtorrent itself are built with:

- `-Os` — optimize for size
- `-g` — emit debug info (preserved in final binary)
- `-flto` — full link-time optimization (applied to both compile and link steps)
- `-w` — suppress all compiler warnings
- `-s` is **not** used — debug symbols are kept in the final binary

These flags are set in `toolchain.py` for both CMake (`CMAKE_C_FLAGS_INIT`, `CMAKE_CXX_FLAGS_INIT`, `CMAKE_EXE_LINKER_FLAGS_INIT`) and autotools (`CFLAGS`, `LDFLAGS`) builds. The rtorrent-specific `LDFLAGS` in `rtorrent.py` also omits `-s`.

## Conventions

- Python 3.12+ (`X | Y` union syntax, `from __future__ import annotations`)
- Naming: `UPPER_CASE` constants, `PascalCase` builders, `snake_case` functions
- Double quotes, spaces (not tabs), LF line endings
- No comments unless explaining non-obvious logic
- Package manager: uv (via `uv.lock`)
- Build backend: pdm-backend
