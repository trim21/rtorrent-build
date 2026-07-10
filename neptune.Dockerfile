FROM gcr.io/distroless/static-debian12@sha256:22fd79fd75eab2372585b44517f8a094349938919dc613aafc37e4bdc9967c82

COPY neptune /usr/local/bin/neptune

ENTRYPOINT ["/usr/local/bin/neptune"]
