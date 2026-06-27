# rtorrent-build

Statically (or glibc only) linked [rtorrent](https://github.com/rakshasa/rtorrent) and [qBittorrent](https://github.com/qbittorrent/qBittorrent) binaries for Linux amd64, built with [Zig](https://ziglang.org/) as the C/C++ toolchain.

## Docker Images

Prebuilt distroless Docker images are available at [`ghcr.io/trim21/rtorrent`](https://github.com/trim21/rtorrent-static/pkgs/container/rtorrent).
Images are built and pushed when a git tag (`v*`) is pushed.

All images are based on `gcr.io/distroless/cc-debian13` (glibc 2.40) and include `busybox` for shell utilities.

### rtorrent 0.9.8

| Tag | Arch |
|---|---|
| `ghcr.io/trim21/rtorrent:0.9.8.amd.v1` | x86_64-v1 |
| `ghcr.io/trim21/rtorrent:0.9.8.amd.v3` | x86_64-v3 |

### rtorrent 0.16 (0.16.15)

| Tag | Arch |
|---|---|
| `ghcr.io/trim21/rtorrent:0.16.15.amd.v1` | x86_64-v1 |
| `ghcr.io/trim21/rtorrent:0.16.15.amd.v3` | x86_64-v3 |
| `ghcr.io/trim21/rtorrent:0.16.amd.v1` | x86_64-v1 |
| `ghcr.io/trim21/rtorrent:0.16.amd.v3` | x86_64-v3 |

### rtorrent master (git snapshot)

| Tag | Arch |
|---|---|
| `ghcr.io/trim21/rtorrent:master.amd.v1` | x86_64-v1 |
| `ghcr.io/trim21/rtorrent:master.amd.v3` | x86_64-v3 |

## GitHub Release Assets

Static binaries are published to [GitHub Releases](https://github.com/trim21/rtorrent-static/releases) on tag pushes.
Binaries are built with `-O2 -flto -fPIC -g` and statically linked except for glibc-family `.so` deps (or fully static with musl).

## Troubleshooting

### qBittorrent: "unspecified system error" / HTTPS tracker failures

This is caused by OpenSSL being unable to find a CA certificate bundle. The statically-linked OpenSSL is compiled with
`--openssldir=/etc/ssl`, which matches Debian/Ubuntu/Arch/Alpine. If your distribution stores CA certificates
elsewhere (e.g. RHEL/Fedora uses `/etc/pki/tls`), set the `SSL_CERT_FILE` environment variable:

```bash
# RHEL/Fedora
SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt qbittorrent-nox

# Or point to a Mozilla CA bundle from the ca-certificates package
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt qbittorrent-nox
```

rtorrent is unaffected — it uses libcurl for HTTPS, which has its own CA bundle auto-detection.

## Build Flags

All binaries are built with `-O2 -flto -fPIC -g -w`:

| Flag | Purpose |
|---|---|
| `-O2` | Optimize for speed |
| `-flto` | Link-time optimization |
| `-fPIC` | Position-independent code |
| `-g` | Debug symbols (preserved in final binary) |
| `-w` | Suppress all compiler warnings |

Architecture-specific `-march` flags are set according to the target microarchitecture level.
