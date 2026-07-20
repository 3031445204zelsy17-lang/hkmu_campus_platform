#!/bin/sh
# Build css/app.min.css = Tailwind utilities + the custom component CSS.
#
# Why concat instead of @import in input.css: postcss-import silently drops
# @import statements that appear after the @tailwind directives (CSS spec
# requires @import to precede other rules), so the custom CSS never made it
# into the bundle. Concatenating @tailwind directives + the eight custom CSS
# files into ONE input, then running tailwindcss, makes Tailwind pass the
# custom CSS through AND minify it — and the custom CSS lands AFTER the
# generated utilities, matching the old load order (custom overrides
# Tailwind preflight/utilities).
#
# Run via `npm run build:css` (PATH includes node_modules/.bin) or `sh
# build-css.sh` from the Docker/CI node stage after `npm ci`.
set -e
cd "$(dirname "$0")"

{
  printf '@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\n'
  cat css/main.css css/nav.css css/auth.css css/community.css \
      css/academic.css css/profile.css css/news.css css/lostfound.css \
      css/messages.css
} > src/_build_input.css

./node_modules/.bin/tailwindcss -i src/_build_input.css -o css/app.min.css --minify

rm -f src/_build_input.css
