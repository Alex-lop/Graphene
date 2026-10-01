# linux/arm64 image for comparator: landrun (Landlock sandbox) built from source, plus git and curl.
# elan, the Lean toolchain, Mathlib and the tools live on the bind-mounted /work, not in the image.
FROM golang:1.24-bookworm AS landrun
RUN git clone https://github.com/Zouuup/landrun /src/landrun \
 && cd /src/landrun && git checkout 811cfff51ceaf3d9843708aa6d22e9b84ccac8b4 \
 && CGO_ENABLED=0 go build -o /landrun ./cmd/landrun

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates zstd procps time \
 && rm -rf /var/lib/apt/lists/*
COPY --from=landrun /landrun /usr/local/bin/landrun
# comparator must not run as a privileged user (its README, assumption 6)
RUN useradd -m -u 1000 judge
USER judge
WORKDIR /work
