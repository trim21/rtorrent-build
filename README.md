# rtorrent-static

Statically-linked [rtorrent](https://github.com/rakshasa/rtorrent) and [qBittorrent](https://github.com/qbittorrent/qBittorrent) binaries for Linux amd64, built with [Zig](https://ziglang.org/) as the C/C++ toolchain.

## Docker Images

Prebuilt distroless Docker images are available at [`ghcr.io/trim21/rtorrent`](https://github.com/trim21/rtorrent-static/pkgs/container/rtorrent).

### rtorrent 0.9.8

| Tag | Arch | glibc |
|---|---|---|
| `ghcr.io/trim21/rtorrent:0.9.8.amd.v1` | x86_64-v1 | 2.17 |
| `ghcr.io/trim21/rtorrent:0.9.8.amd.v3` | x86_64-v3 | 2.17 |

### rtorrent 0.16 (0.16.13)

| Tag | Arch | glibc |
|---|---|---|
| `ghcr.io/trim21/rtorrent:0.16.13.amd.v1` | x86_64-v1 | 2.28 |
| `ghcr.io/trim21/rtorrent:0.16.amd.v1` | x86_64-v1 | 2.28 |
| `ghcr.io/trim21/rtorrent:0.16.13.amd.v3` | x86_64-v3 | 2.28 |
| `ghcr.io/trim21/rtorrent:0.16.amd.v3` | x86_64-v3 | 2.28 |

### rtorrent master (git snapshot)

| Tag | Arch | glibc |
|---|---|---|
| `ghcr.io/trim21/rtorrent:master.amd.v1` | x86_64-v1 | 2.28 |
| `ghcr.io/trim21/rtorrent:master.amd.v3` | x86_64-v3 | 2.28 |

All images include `busybox` for shell utilities and are based on `gcr.io/distroless/cc-debian13`.

## GitHub Release Assets

Static binaries are published to [GitHub Releases](https://github.com/trim21/rtorrent-static/releases) on tag pushes.

### rtorrent

| Binary | glibc target |
|---|---|
| `rtorrent-0.9.8.amd.v1.glibc.2.17` | 2.17 |
| `rtorrent-0.9.8.amd.v1-musl` | musl |
| `rtorrent-0.16.13.amd.v1.glibc.2.28` | 2.28 |
| `rtorrent-0.16.13.amd.v1-musl` | musl |

### qBittorrent

| Binary | qBittorrent | libtorrent | glibc target |
|---|---|---|---|
| `qb-5.1.4-lt-1.2.20.amd.v1.glibc.2.34` | 5.1.4 | 1.2.20 | 2.34 |
| `qb-5.1.4-lt-1.2.20.amd.v1-musl` | 5.1.4 | 1.2.20 | musl |
| `qb-5.1.4-lt-2.0.12.amd.v1.glibc.2.34` | 5.1.4 | 2.0.12 | 2.34 |
| `qb-5.1.4-lt-2.0.12.amd.v1-musl` | 5.1.4 | 2.0.12 | musl |
| `qb-5.2.1-lt-1.2.20.amd.v1.glibc.2.34` | 5.2.1 | 1.2.20 | 2.34 |
| `qb-5.2.1-lt-1.2.20.amd.v1-musl` | 5.2.1 | 1.2.20 | musl |
| `qb-5.2.1-lt-2.0.12.amd.v1.glibc.2.34` | 5.2.1 | 2.0.12 | 2.34 |
| `qb-5.2.1-lt-2.0.12.amd.v1-musl` | 5.2.1 | 2.0.12 | musl |

All binaries are built with `-Os -flto -fPIC -g` and x86_64-v1 baseline, statically linked except for glibc-family `.so` deps.
