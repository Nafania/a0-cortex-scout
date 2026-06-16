#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-3.3.7}"
TAG="v${VERSION#v}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${RUNNER_TEMP:-$ROOT/.build}/cortex-scout-linux-x64"
DIST="$ROOT/dist"
UPSTREAM="https://github.com/cortex-works/cortex-scout.git"

rm -rf "$WORK" "$DIST"
mkdir -p "$WORK" "$DIST"

git clone --depth 1 --branch "$TAG" "$UPSTREAM" "$WORK/source"

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends \
    protobuf-compiler libprotobuf-dev pkg-config ca-certificates cmake clang make perl
fi

cd "$WORK/source/mcp-server"
cargo build --release --bin cortex-scout --bin cortex-scout-mcp

PKG="cortex-scout-${VERSION#v}-linux-x64"
PKG_DIR="$WORK/$PKG"
mkdir -p "$PKG_DIR"
cp target/release/cortex-scout target/release/cortex-scout-mcp "$PKG_DIR/"
cp "$WORK/source/LICENSE" "$WORK/source/README.md" "$WORK/source/server.json" "$PKG_DIR/"
printf "%s\n" "${VERSION#v}" > "$PKG_DIR/VERSION"

tar -C "$PKG_DIR" -czf "$DIST/$PKG.tar.gz" .
sha256sum "$DIST/$PKG.tar.gz" | tee "$DIST/$PKG.tar.gz.sha256"
