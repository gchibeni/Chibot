#!/usr/bin/env bash
# Launch Chibot.
# "uv run" syncs the environment from uv.lock before starting, so a fresh
# clone needs nothing but uv installed. --project makes this work from any
# directory; the bot itself moves to the project root on startup.
set -euo pipefail
exec uv run --project "$(dirname "$0")" chibot "$@"
