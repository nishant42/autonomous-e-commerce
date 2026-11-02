#!/bin/sh
set -eu
cd shop/apps/storefront
exec ../../node_modules/.bin/next start --hostname 0.0.0.0 --port "${PORT:-8000}"
