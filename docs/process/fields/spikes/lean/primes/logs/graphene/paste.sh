#!/usr/bin/env bash
# An $EDITOR for `graphene plan edit`: keeps what it was shown, replaces it with $PASTE (a file).
cp "$1" "${SHOWN:-/dev/null}"
cp "$PASTE" "$1"
