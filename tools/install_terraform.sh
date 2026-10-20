#!/usr/bin/env bash
# Install the pinned Terraform 1.15.8 (linux_amd64) for CI fmt/validate only.
# The archive digest is pinned; a mismatch aborts before anything is unpacked.
set -euo pipefail

VERSION="1.15.8"
SHA256="d25ce7b6902013ad905db3d2eab0be4cd905887fe88b81a6171b8d5503c31f3d"
DEST="${1:-$HOME/.local/bin}"
ARCHIVE="terraform_${VERSION}_linux_amd64.zip"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  --output "$WORK/$ARCHIVE" "https://releases.hashicorp.com/terraform/${VERSION}/${ARCHIVE}"
echo "${SHA256}  $WORK/$ARCHIVE" | sha256sum --check --strict -
mkdir -p "$DEST"
unzip -o -q "$WORK/$ARCHIVE" terraform -d "$DEST"
"$DEST/terraform" version
