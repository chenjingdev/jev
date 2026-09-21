#!/bin/sh
# Builds Rapfi (https://github.com/dhbloo/rapfi, GPLv3; weights CC0) into gomoku/rapfi/.
# Needs git, cmake and a C++17 compiler. Apple silicon gets the NEON build; pass
# other -DUSE_* flags on x86 (see the Rapfi README).
set -eu
here=$(cd "$(dirname "$0")" && pwd)
src=${TMPDIR:-/tmp}/rapfi-src
dst="$here/rapfi"
[ -d "$src/.git" ] || git clone --depth 1 --recurse-submodules --shallow-submodules https://github.com/dhbloo/rapfi.git "$src"
case $(uname -m) in
  arm64|aarch64) flags="-DUSE_NEON=ON -DUSE_NEON_DOTPROD=ON" ;;
  *) flags="" ;;
esac
cmake -S "$src/Rapfi" -B "$src/Rapfi/build" -DCMAKE_BUILD_TYPE=Release $flags >/dev/null
cmake --build "$src/Rapfi/build" -j "$(sysctl -n hw.ncpu 2>/dev/null || nproc)"
mkdir -p "$dst"
cp "$src/Rapfi/build/pbrain-rapfi" "$src/Networks/config-example/config.toml" \
   "$src/Networks/classical/"*.bin "$src/Networks/mix9svq/"*.lz4 "$dst/"
printf 'START 15\nINFO rule 4\nINFO timeout_turn 300\nBEGIN\nEND\n' | (cd "$dst" && ./pbrain-rapfi) | grep -E '^[0-9]+,[0-9]+$' >/dev/null && echo "rapfi ready in $dst"
