#!/bin/bash
# Builds kit/server/vm/qagame.qvm: World of PADMAN 1.7.0's server game code plus spawn-protect.patch
# (the g_spawnProtect setting from WoP's newer code). A .qvm runs on every OS, so one build serves all.
#
# Needs Linux with git, cmake, gcc and ninja. From this repo, on any computer with Docker:
#   docker run --rm -v "$PWD:/kit" -w /kit ubuntu:24.04 bash kit/server/game/build-qvm.sh
# The result goes to kit/server/vm/qagame.qvm; put its SHA-256 in kit/kit.json ("patched_qagame_sha256").
set -euo pipefail

TAG="v1.7.0"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/../vm/qagame.qvm"
WORK="$(mktemp -d)"

if ! command -v cmake >/dev/null || ! command -v ninja >/dev/null || ! command -v pkg-config >/dev/null || ! command -v faketime >/dev/null; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git cmake gcc g++ ninja-build pkg-config libsdl2-dev libcurl4-openssl-dev faketime >/dev/null
fi

# Only the code: the game data (wop/) is gigabytes and not needed to build the server code
git clone --quiet --filter=blob:none --no-checkout --depth 1 --branch "$TAG" \
    https://github.com/PadWorld-Entertainment/worldofpadman.git "$WORK/src"
cd "$WORK/src"
git sparse-checkout set --no-cone '/*' '!/wop/' '!/XTRAS/' '!/xmas/' '!/misc/'
git checkout --quiet
git apply "$HERE/spawn-protect.patch"
# WoP's build also packs the game data from these folders; empty stand-ins skip that
for data in wop xmas misc; do
    mkdir -p "$data"
    : > "$data/CMakeLists.txt"
done

cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_CLIENT=OFF -DBUILD_SERVER=OFF -DBUILD_TESTS=OFF \
    | tail -n 5
# The compiler stamps in its date (the gamedate setting); use the official 1.7.0 build date, so every build is
# byte for byte the same (an unpatched build then equals the qagame.qvm in wop_vm_1.7.0.pk3)
faketime "2024-12-01 12:00:00" cmake --build build --target qvm_qagame

built="$(find . -path "*/vm/qagame.qvm" | head -n 1)"
mkdir -p "$(dirname "$OUT")"
cp "$built" "$OUT"
sha256sum "$OUT"
