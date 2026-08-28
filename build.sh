#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export DOTNET_ROOT="${DOTNET_ROOT:-$HOME/.dotnet}"
export PATH="$DOTNET_ROOT:$PATH"

dotnet build -c Release "$@"

echo
echo "已部署到：$HOME/Library/Application Support/unity.Klei.Oxygen Not Included/mods/Local/ONI-Anti-Entropy-Generator"
