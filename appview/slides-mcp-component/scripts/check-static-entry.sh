#!/bin/sh
# Check the entry referenced by this candidate bundle exists. This does not
# qualify the compiler, application behavior, state migration, or release.
set -eu
public=$(CDPATH= cd -- "$(dirname -- "$0")/../cljs/public" && pwd)
if [ ! -s "$public/js/app.js" ]; then
  printf '%s\n' 'FAIL: static entry js/app.js is missing or empty' >&2
  exit 1
fi
printf '%s\n' 'OK: static entry exists; application and release are not qualified'
