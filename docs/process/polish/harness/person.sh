#!/bin/sh
# person.sh <command...>: run it with a person's environment, as a WezTerm window you opened would
exec env -i HOME="$HOME" USER="$USER" LOGNAME="$USER" SHELL=/bin/zsh TERM=xterm-256color LANG=en_US.UTF-8 \
  PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" EDITOR=vi TMPDIR="$TMPDIR" "$@"
