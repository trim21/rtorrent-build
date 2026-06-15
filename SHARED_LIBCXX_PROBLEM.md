# Shared libc++ Problem

## Goal

`--linkage shared` mode: all dependency libs built as `.so`, binary links them dynamically. Requires a **shared libc++/libc++abi/libunwind** because zig's static C++ runtime has hidden-visibility symbols that can't be exported by the final executable (even with `--whole-archive` + `--export-dynamic`).

## The Core Problem

`build_cxx_shared_lib()` in `src/rtorrent_builder/toolchain.py:387` tries to build `libc++_shared.so` using:

```bash
zig c++ -target x86_64-linux-gnu.2.40 -shared -fPIC -o libc++_shared.so \
  -Wl,--whole-archive -lc++ -lc++abi -lunwind -Wl,--no-whole-archive
```

**This fails with:** `version '.2.40' in target triple 'x86_64-unknown-linux-gnu.2.40' is invalid`

### Why?

Zig's pip package (`ziglang` on PyPI) ships **only source code** for libc++/libc++abi/libunwind — no pre-compiled `.a` files. Compilation happens on-the-fly:

- `zig c++ -target x86_64-linux-gnu.2.40 foo.cpp` → zig compiles libc++ from source into a cache dir (`~/.cache/zig/o/<hash>/libc++.a`), then links via **LLD** (zig's built-in linker). This **works**.
- `zig c++ -target x86_64-linux-gnu.2.40 -lc++` → zig tries to resolve `-lc++` via its glibc sysroot, finds no sysroot for glibc 2.40, and **fails** with `version invalid`.

The `-target` flag is needed to force zig's internal toolchain (LLD + bundled C++ headers). Without version suffix (`x86_64-linux-gnu`), zig delegates to system linker (`/usr/bin/ld`) which knows nothing about zig's bundled C++ libs.

### Things That Don't Work

| Approach | Result |
|---|---|
| `zig c++ -target x86_64-linux-gnu.2.40 -shared -Wl,--whole-archive -lc++ ...` | Version validation fails |
| `zig c++ -shared -lc++ ...` (no `-target`) | System linker (`/usr/bin/ld`) can't find libc++ |
| `zig c++ -fuse-ld=lld` | zig rejects this flag |
| `zig build-lib -dynamic` without source files | zig requires source |

## Solution: Compile from Source (zig_shared_libcxx approach)

https://github.com/naleraphael/zig_shared_libcxx

This repo builds shared libc++/libc++abi (and static libunwind) **from zig's bundled source code**. Key file: `build_utils.zig` contains exact file lists and compiler flags.

The approach: instead of `-lc++`, pass the actual `.cpp`/`.c`/`.S` source files from zig's lib dir directly. Since these are compiled (not looked up via `-l`), zig doesn't do version validation.

### Source Files Location

Zig's lib dir = `<venv>/lib/python3.12/site-packages/ziglang/lib/`

```
libcxx/src/*.cpp         (45 files)
libcxxabi/src/*.cpp       (19 files, some conditional on target/threading)
libunwind/src/*.cpp       (3 files)
libunwind/src/*.c         (5 files)
libunwind/src/*.S         (2 files, assembly)
```

See `build_utils.zig` lines 32-139 for exact file lists.

### Required Compiler Flags

See `build_utils.zig` `addCxxArgs()` (line 572), `buildLibCxx()` (line 288), `buildLibCxxAbi()` (line 394), `buildLibUnwind()` (line 488), `addUnwindArgs()` (line 639).

Key flags:
- `-fvisibility=hidden -fvisibility-inlines-hidden` (NOT `_LIBCPP_DISABLE_VISIBILITY_ANNOTATIONS`)
- `-D_LIBCPP_BUILDING_LIBRARY`, `-D_LIBCXX_BUILDING_LIBCXXABI`, `-D_LIBCXXABI_BUILDING_LIBRARY`
- `-nostdinc++`
- Include paths for `libcxx/include`, `libcxxabi/include`, `libunwind/include`, `libcxx/src`

### Important Note from Repo

libunwind must be **statically linked** (`build_utils.zig:563`). The shared libc++_shared.so statically embeds libunwind.

## Possible Implementation Paths

### Path A: Python-based compilation (Recommended)

In `build_cxx_shared_lib()`, instead of calling `zig c++ -shared -lc++ ...`:

1. Find zig's lib dir (`_zig_lib_dir` property already exists at `toolchain.py:436`)
2. Collect all source files from `libcxx/src`, `libcxxabi/src`, `libunwind/src`
3. Construct compiler/linker flags based on `build_utils.zig`
4. Use one-shot `zig c++ -shared -fPIC $(FLAGS) $(SOURCES) -o libc++_shared.so`

```python
zig c++ -target x86_64-linux-gnu.2.40 -shared -fPIC -fvisibility=hidden \
  -I{zig_lib}/libcxx/include -I{zig_lib}/libcxxabi/include \
  -I{zig_lib}/libunwind/include -I{zig_lib}/libcxx/src \
  -nostdinc++ -std=c++23 \
  -D_LIBCPP_BUILDING_LIBRARY -D_LIBCXX_BUILDING_LIBCXXABI \
  -D_LIBCXXABI_BUILDING_LIBRARY -D_LIBCPP_ABI_VERSION=1 \
  ... (rest of flags from build_utils.zig)
  {zig_lib}/libcxx/src/*.cpp \
  {zig_lib}/libcxxabi/src/*.cpp \
  {zig_lib}/libunwind/src/*.cpp {zig_lib}/libunwind/src/*.c \
  -x assembler-with-cpp {zig_lib}/libunwind/src/*.S \
  -o libc++_shared.so
```

Pros: No zig build.zig dependency, fits current Python-based build system.
Cons: Must maintain file lists and flags; ~70 source files to compile.

### Path B: Use zig's build system

Install zig (not pip ziglang) and use this repo's `build_utils.zig` via `zig build`. The output `.so` files can then be copied to `install_prefix/lib/`.

Cons: Requires system zig install (not pip), adds zig build.zig to project.

### Path C: Drop `--linkage shared`, use `--allow-shlib-undefined`

Just let `.so` deps have undefined C++ symbols at build time (`--allow-shlib-undefined` is already in `CMAKE_SHARED_LINKER_FLAGS_INIT`). Link libc++ statically into the final binary with `--export-dynamic`. If hidden-visibility symbols truly prevent this, revert to fully-static builds.

## Relevant Files

- `src/rtorrent_builder/toolchain.py` — `build_cxx_shared_lib()` (line 387), `_zig_lib_dir` (line 436), `_target_triple` (line 279)
- `src/rtorrent_builder/builder.py` — `_build_pkg()` calls `build_cxx_shared_lib()` at line 345
- `src/rtorrent_builder/deps/rtorrent.py` — uses `tc.executable_ldflags` (`-lc++_shared --export-dynamic`)
- `build_utils.zig` in https://github.com/naleraphael/zig_shared_libcxx — reference implementation with exact file lists and flags
