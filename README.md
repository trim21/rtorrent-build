# rtorrent-build

Statically (or glibc only) linked [rtorrent](https://github.com/rakshasa/rtorrent) and [qBittorrent](https://github.com/qbittorrent/qBittorrent) binaries for Linux amd64, built with [Zig](https://ziglang.org/) as the C/C++ toolchain.

### rtorrent

| Variant | Version | Glibc Target |
|---|---|---|
| `rtorrent-0.16` | 0.16.17 | 2.34 |
| `rtorrent-0.9.8` | 0.9.8 | 2.17 |
| `rtorrent-master` | `2354c9cdb501` (git) | 2.34 |


### qBittorrent

| Variant | Version | Glibc Target |
|---|---|---|
| `qbittorrent-5.1-lt1` | 5.1.4 | 2.34 |
| `qbittorrent-5.1-lt2` | 5.1.4 | 2.34 |
| `qbittorrent-5.2-lt1` | 5.2.3 | 2.34 |
| `qbittorrent-5.2-lt2` | 5.2.3 | 2.34 |


### Transmission

| Variant | Version | Glibc Target |
|---|---|---|
| `transmission` | 4.1.3 | 2.28 |


## Docker Images

Prebuilt distroless Docker images are available at [`ghcr.io/trim21/rtorrent`](https://github.com/trim21/rtorrent-static/pkgs/container/rtorrent). Images are built and pushed when a git tag (`v*`) is pushed.

All images are based on `gcr.io/distroless/cc-debian13` (glibc 2.40) and include `busybox` for shell utilities.

### rtorrent

#### rtorrent 0.16

| Tag | Arch |
|---|---|
| `0.amd.v1` | x86_64-v1 |
| `0.16.amd.v1` | x86_64-v1 |
| `0.16.17.amd.v1` | x86_64-v1 |
| `0.amd.v3` | x86_64-v3 |
| `0.16.amd.v3` | x86_64-v3 |
| `0.16.17.amd.v3` | x86_64-v3 |


#### rtorrent 0.9.8

| Tag | Arch |
|---|---|
| `0.amd.v1` | x86_64-v1 |
| `0.9.amd.v1` | x86_64-v1 |
| `0.9.8.amd.v1` | x86_64-v1 |
| `0.amd.v3` | x86_64-v3 |
| `0.9.amd.v3` | x86_64-v3 |
| `0.9.8.amd.v3` | x86_64-v3 |


#### rtorrent master

| Tag | Arch |
|---|---|
| `master.amd.v1` | x86_64-v1 |
| `master.amd.v3` | x86_64-v3 |


## Build

```bash
python build.py build manifests/rtorrent-master.jsonc
```

### CLI Options

| Option | Values | Description |
|---|---|---|
| `--libc` | `glibc` (default), `musl`, `current` | glibc dynamic link / musl fully static / host glibc |
| `--arch` | `amd/v1` (default), `amd/v2`, `amd/v3`, `amd/v4`, `native` | x86-64 microarchitecture level |
| `--docker` | — | Build distroless Docker image |
| `--disguise` | — | Spoof rtorrent/0.9.8 User-Agent |
| `--debug/--no-debug` | — | Debug build: `-g -O0`, no LTO |
| `--no-cache` | — | Disable build cache |
| `-j N` | — | Max concurrent package builds (default: 1) |

## Troubleshooting

### qBittorrent: 'unspecified system error' / HTTPS tracker failures

This is caused by OpenSSL being unable to find a CA certificate bundle. The statically-linked OpenSSL is compiled with `--openssldir=/etc/ssl`, which matches Debian/Ubuntu/Arch/Alpine. If your distribution stores CA certificates elsewhere (e.g. RHEL/Fedora uses `/etc/pki/tls`), set the `SSL_CERT_FILE` environment variable:

```bash
# RHEL/Fedora
SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt qbittorrent-nox

# Or point to a Mozilla CA bundle from the ca-certificates package
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt qbittorrent-nox
```

rtorrent is unaffected — it uses libcurl for HTTPS, which has its own CA bundle auto-detection.
