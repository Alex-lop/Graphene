#!/usr/bin/env bash
# mux.sh <80x24|120x36> <wezterm cli command…>: run it against that isolated mux (start.sh)
size=$1; shift; SOCKS=${SOCKS:-/tmp/graphene-mux}
export WEZTERM_UNIX_SOCKET="$SOCKS/sock-$size" WEZTERM_CONFIG_FILE="$SOCKS/wez-$size.lua"
exec wezterm cli --prefer-mux --no-auto-start "$@"
