#!/bin/sh
# shoot.sh OUT.png WIDTH HEIGHT "query": the graph's preview page (editors/vscode/media/preview.html, after
# `npm run build` there) in headless Chrome, at twice the pixels. The query is the page's own:
#   fixture=running&theme=cursor            a fixture, in Cursor Dark (also plus, light, hc)
#   state=file:///abs/state.json&theme=hc   a real session's snapshot, written to a file for the picture
# The before and after pictures of the sessions run were taken with it (look/README.md).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
PAGE="$HERE/../../../editors/vscode/media/preview.html"
CHROME=${CHROME:-"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 --allow-file-access-from-files \
  --user-data-dir="$(dirname "$1")/.chrome-profile" --virtual-time-budget=4000 --window-size="$2,$3" \
  --screenshot="$1" "file://$PAGE?$4" >/dev/null 2>&1
echo "$1"
