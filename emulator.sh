#!/bin/zsh
set -eu
ROOT="${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export DYLD_LIBRARY_PATH="$(brew --prefix mgba)/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
exec uv run --no-project --python "$ROOT/.venv/bin/python" "$ROOT/emulator.py" "$@"
