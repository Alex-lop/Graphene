#!/usr/bin/env bash
# An $EDITOR for `graphene plan edit`: keeps what it was shown, turns every "? " proposal into "- ".
cp "$1" "${SHOWN:-/dev/null}"
sed -i '' -E 's/^( *)\? /\1- /' "$1"
