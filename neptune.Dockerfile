FROM gcr.io/distroless/static-debian12

COPY neptune /usr/local/bin/neptune

ENTRYPOINT ["/usr/local/bin/neptune"]
