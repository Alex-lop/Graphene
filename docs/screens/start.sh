#!/usr/bin/env bash
# start.sh <80x24|120x36>: an isolated WezTerm mux server of that size, with a person's environment
# (no agent's marks), so `graphene watch` in it behaves as it does for you. Its socket and config live
# under $SOCKS (default /tmp/graphene-mux); a mux of your own is never touched.
S=$(cd "$(dirname "$0")" && pwd); size=$1; SOCKS=${SOCKS:-/tmp/graphene-mux}; mkdir -p "$SOCKS/home-$size"
cat > "$SOCKS/wez-$size.lua" <<LUA
return {
  unix_domains = { { name = 'm$size', socket_path = '$SOCKS/sock-$size' } },
  initial_cols = ${size%x*}, initial_rows = ${size#*x},
  default_prog = { '/bin/zsh', '-f' },
  set_environment_variables = { HOME = '$HOME' },
}
LUA
rm -f "$SOCKS/sock-$size"
# HOME is the mux's own while it starts: wezterm keeps one pid file per HOME, and one may be running
env -i HOME="$SOCKS/home-$size" USER="$USER" PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  LANG=en_US.UTF-8 TERM=xterm-256color WEZTERM_CONFIG_FILE="$SOCKS/wez-$size.lua" \
  wezterm-mux-server --daemonize --config-file "$SOCKS/wez-$size.lua"
