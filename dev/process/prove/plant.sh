#!/usr/bin/env bash
# The plant, as the loop night planted it (dev/process/loop/lane1-evidence.md:84-95): after the leaves
# land, the person breaks the xml sku key in normalize/fields.py and commits, adds an end-to-end leaf,
# accepts and runs; when it comes back with the r offer, takes it by the command the run printed, and
# runs again. Writes RUN/plant.txt, add.txt, run2.txt, reopen.txt, run3.txt; appends to seconds.txt.
#
#   dev/process/prove/plant.sh RUN              (a newrun.sh run directory after its main run)
set -euo pipefail
. "$(dirname "$0")/common.sh"
RUN=$1
. "$RUN/env.sh"
t0=$(date +%s)
f=normalize/fields.py
if grep -q '"code"' "$f"; then
  python3 - "$f" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
p.write_text(p.read_text(encoding="utf-8").replace('"code"', '"xcode"', 1), encoding="utf-8")
PY
  echo "planted: \"code\" -> \"xcode\" in $f" > "$RUN/plant.txt"
else
  printf '\n# planted: no "code" key here to break\n' >> "$f"
  echo "planted: no \"code\" key in $f; a comment was appended instead" > "$RUN/plant.txt"
fi
git add "$f" && git commit -qm "planted: the xml sku key" && git rev-parse HEAD >> "$RUN/plant.txt"
printf 'git commit: planted the xml sku key' | log handwork > /dev/null
as_me graphene node add "end to end: the xml feed loads" --id e2e-xml --scope tests/test_e2e_xml.py \
  --goal "tests/test_e2e_xml.py: load samples/prices.xml through cli.main and check the records that come out, sku and price_cents included." \
  --check "python3 -m unittest tests.test_e2e_xml -q" > "$RUN/add.txt" 2>&1 || true
printf 'as_me graphene node add e2e-xml' | log shape > /dev/null
as_me graphene plan accept >> "$RUN/accept.txt" 2>&1 || true
printf 'as_me graphene plan accept' | log accept > /dev/null
printf 'as_me graphene run --parallel 3' | log run > /dev/null
as_me graphene run --parallel 3 > "$RUN/run2.txt" 2>&1 || true
log read < "$RUN/run2.txt" > /dev/null
r=$(grep -o '`graphene node reopen [^`]*`' "$RUN/run2.txt" | head -1 | tr -d '`' || true)
if [ -n "$r" ]; then
  echo "r offer: $r" >> "$RUN/plant.txt"
  printf '%s' "as_me $r" | log reopen > /dev/null
  eval "as_me $r" > "$RUN/reopen.txt" 2>&1 || true
  printf 'as_me graphene run --parallel 3' | log run > /dev/null
  as_me graphene run --parallel 3 > "$RUN/run3.txt" 2>&1 || true
  log read < "$RUN/run3.txt" > /dev/null
else
  echo "r offer: none printed (run2.txt has no reopen command)" >> "$RUN/plant.txt"
fi
echo "plant $(( $(date +%s) - t0 ))" >> "$RUN/seconds.txt"
