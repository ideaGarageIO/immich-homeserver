# takeout2immich worker: Python + pinned rclone + pinned immich-go.
FROM python:3.12-slim AS tools

ARG TARGETARCH
ARG RCLONE_VERSION=v1.76.0
ARG RCLONE_SHA256_AMD64=b00f00b3266c3764413afe599d3ec316f6f43b3e0ea8a0bc1d186d2133e46df7
ARG RCLONE_SHA256_ARM64=ee169016675e23a69d77240565133ff7dbc9b33d16fa8f7053d4af39f1eaeb78
ARG IMMICH_GO_VERSION=v0.32.0
ARG IMMICH_GO_SHA256_AMD64=6e2ad86bafdadb9466d6515de7cb882726c0aea1a21d51164dff361d7d480a97
ARG IMMICH_GO_SHA256_ARM64=2c35d9284baae407ef9540bdac5f488971b0bdc7be758a4d7c05ab270af09fdb

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="${TARGETARCH:-amd64}"; \
    case "$arch" in \
      amd64) r_sha="$RCLONE_SHA256_AMD64"; ig_arch=x86_64; ig_sha="$IMMICH_GO_SHA256_AMD64" ;; \
      arm64) r_sha="$RCLONE_SHA256_ARM64"; ig_arch=arm64;  ig_sha="$IMMICH_GO_SHA256_ARM64" ;; \
      *) echo "unsupported arch $arch"; exit 1 ;; \
    esac; \
    cd /tmp; \
    curl -fsSLo rclone.zip "https://downloads.rclone.org/${RCLONE_VERSION}/rclone-${RCLONE_VERSION}-linux-${arch}.zip"; \
    echo "${r_sha}  rclone.zip" | sha256sum -c -; \
    unzip -q rclone.zip; install -m 0755 rclone-*/rclone /usr/local/bin/rclone; \
    curl -fsSLo immich-go.tgz "https://github.com/simulot/immich-go/releases/download/${IMMICH_GO_VERSION}/immich-go_Linux_${ig_arch}.tar.gz"; \
    echo "${ig_sha}  immich-go.tgz" | sha256sum -c -; \
    tar -xzf immich-go.tgz immich-go; install -m 0755 immich-go /usr/local/bin/immich-go


FROM python:3.12-slim

LABEL org.opencontainers.image.title="immich-importer" \
      org.opencontainers.image.description="takeout2immich: Google Photos Takeout -> Immich" \
      org.opencontainers.image.licenses="MIT"

COPY --from=tools /usr/local/bin/rclone /usr/local/bin/immich-go /usr/local/bin/

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && rm -rf /root/.cache

ENV TAKEOUT2IMMICH_HOME=/data/importer \
    HOME=/tmp \
    PYTHONUNBUFFERED=1 \
    TERM=xterm-256color
RUN mkdir -p /data/importer /data/staging && chmod 0777 /data/importer /data/staging

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["takeout2immich", "health"]

ENTRYPOINT ["takeout2immich"]
CMD ["watch"]
