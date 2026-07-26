#!/usr/bin/env pwsh
# Launch Chibot.
# "uv run" syncs the environment from uv.lock before starting, so a fresh
# clone needs nothing but uv installed. --project makes this work from any
# directory; the bot itself moves to the project root on startup.
uv run --project $PSScriptRoot chibot @args
