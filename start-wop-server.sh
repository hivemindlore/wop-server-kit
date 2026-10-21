#!/bin/bash
# WoP Server Kit for Mac. Open Terminal and paste:
#   curl -fsSL https://raw.githubusercontent.com/OWNER/wop-server-kit/main/start-wop-server.sh | bash
# First run: gets uv (which provides Python) and the kit, then hands over to kit/setup/wopkit.py.
set -euo pipefail

# Everything is inside main(): with `curl | bash`, bash reads this script from the pipe, so the
# whole function must be read before anything runs. The keyboard (/dev/tty) is given only to the
# programs that ask questions.
main() {
REPO="OWNER/wop-server-kit"      # the GitHub repo with this kit
BRANCH="main"
UV_VERSION="0.9.2"
UV_SHA_ARM="90b1e69da3d04772565dd556ae8e72c86bdb7da85a8dfc2c6b50c400b0e6aa97"
UV_SHA_INTEL="c887d2c4f629eee99b80a347880870f3bc77f7746db81923efe520f609f80857"

ROOT="${WOP_KIT_ROOT:-$HOME/Library/Application Support/WoPServer}"
TOOLS="$ROOT/tools"

local keyboard=/dev/stdin
if [ ! -t 0 ] && [ -r /dev/tty ]; then keyboard=/dev/tty; fi

if [ -x "$ROOT/wopkit.sh" ]; then
    exec "$ROOT/wopkit.sh" start <"$keyboard"
fi

echo "WoP Server Kit: getting started (this window will ask you a few things)."
mkdir -p "$TOOLS"
TMP="$(mktemp -d)"

if [ ! -x "$TOOLS/uv" ]; then
    echo ">> Downloading the helper that runs the kit (uv, about 20 MB)..."
    if [ "$(uname -m)" = "arm64" ]; then arch="aarch64"; sha="$UV_SHA_ARM"; else arch="x86_64"; sha="$UV_SHA_INTEL"; fi
    curl -fsSL -o "$TMP/uv.tar.gz" "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$arch-apple-darwin.tar.gz"
    if [ "$(shasum -a 256 "$TMP/uv.tar.gz" | cut -d' ' -f1)" != "$sha" ]; then
        echo "The uv download is damaged. Please try again."; exit 1
    fi
    tar -xzf "$TMP/uv.tar.gz" -C "$TMP"
    cp "$TMP/uv-$arch-apple-darwin/uv" "$TOOLS/uv"
    chmod 755 "$TOOLS/uv"
fi

echo ">> Downloading the WoP Server Kit..."
if [ -n "${WOP_KIT_URL:-}" ]; then
    cp "${WOP_KIT_URL#file://}" "$TMP/kit.zip"
else
    curl -fsSL -o "$TMP/kit.zip" "https://github.com/$REPO/archive/refs/heads/$BRANCH.zip"
fi
unzip -q "$TMP/kit.zip" -d "$TMP/kit"
kit_dir="$(find "$TMP/kit" -mindepth 2 -maxdepth 2 -type d -name kit | head -n 1)"
if [ -z "$kit_dir" ]; then echo "The kit download has no kit folder."; exit 1; fi
rm -rf "$ROOT/kit"
cp -R "$kit_dir" "$ROOT/kit"
rm -rf "$TMP"

# uv keeps Python and its downloads inside the kit folder
export UV_CACHE_DIR="$ROOT/cache/uv"
export UV_PYTHON_INSTALL_DIR="$ROOT/python"
export UV_PYTHON_PREFERENCE="only-managed"
exec "$TOOLS/uv" run --quiet --script "$ROOT/kit/setup/wopkit.py" start --no-update <"$keyboard"
}

main "$@"
