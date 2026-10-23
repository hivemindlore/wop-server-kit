#!/bin/bash
# WoP Server Kit for Mac and Linux. Open Terminal and paste:
#   curl -fsSL https://raw.githubusercontent.com/hivemindlore/wop-server-kit/main/start-wop-server.sh | bash
# First run: gets uv (which provides Python) and the kit, then hands over to kit/setup/wopkit.py.
set -euo pipefail

# Everything is inside main(): with `curl | bash`, bash reads this script from the pipe, so the
# whole function must be read before anything runs. The keyboard (/dev/tty) is given only to the
# programs that ask questions.
main() {
REPO="hivemindlore/wop-server-kit"      # the GitHub repo with this kit
BRANCH="main"
UV_VERSION="0.9.2"
UV_SHA_MAC_ARM="90b1e69da3d04772565dd556ae8e72c86bdb7da85a8dfc2c6b50c400b0e6aa97"
UV_SHA_MAC_INTEL="c887d2c4f629eee99b80a347880870f3bc77f7746db81923efe520f609f80857"
UV_SHA_LINUX_ARM="0f0ecf2abcb50f8fb5d2b52c8095af4c133897086e3f2e0259f4fcb3d8ddf273"
UV_SHA_LINUX_INTEL="b775bb84c72210c6c0b9670cfaad0ac2e3953f12a2947d52b57603b4fbae3798"

case "$(uname -s)" in
    Darwin) DEFAULT_ROOT="$HOME/Library/Application Support/WoPServer" ;;
    Linux)  DEFAULT_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/WoPServer" ;;
    *)      echo "Sorry, the WoP Server Kit works on Windows, Mac and Linux only."; exit 1 ;;
esac
ROOT="${WOP_KIT_ROOT:-$DEFAULT_ROOT}"
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
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm64)         target="aarch64-apple-darwin";      sha="$UV_SHA_MAC_ARM" ;;
        Darwin-*)             target="x86_64-apple-darwin";       sha="$UV_SHA_MAC_INTEL" ;;
        Linux-aarch64|Linux-arm64) target="aarch64-unknown-linux-gnu"; sha="$UV_SHA_LINUX_ARM" ;;
        *)                    target="x86_64-unknown-linux-gnu";  sha="$UV_SHA_LINUX_INTEL" ;;
    esac
    curl -fsSL -o "$TMP/uv.tar.gz" "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$target.tar.gz"
    if command -v sha256sum >/dev/null 2>&1; then got="$(sha256sum "$TMP/uv.tar.gz" | cut -d' ' -f1)"
    else got="$(shasum -a 256 "$TMP/uv.tar.gz" | cut -d' ' -f1)"; fi
    if [ "$got" != "$sha" ]; then
        echo "The uv download is damaged. Please try again."; exit 1
    fi
    tar -xzf "$TMP/uv.tar.gz" -C "$TMP"
    cp "$TMP/uv-$target/uv" "$TOOLS/uv"
    chmod 755 "$TOOLS/uv"
fi

echo ">> Downloading the WoP Server Kit..."
if [ -n "${WOP_KIT_URL:-}" ]; then
    cp "${WOP_KIT_URL#file://}" "$TMP/kit.zip"
else
    curl -fsSL -o "$TMP/kit.zip" "https://github.com/$REPO/archive/refs/heads/$BRANCH.zip"
fi
if command -v unzip >/dev/null 2>&1; then unzip -q "$TMP/kit.zip" -d "$TMP/kit"
else python3 -m zipfile -e "$TMP/kit.zip" "$TMP/kit"; fi
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
