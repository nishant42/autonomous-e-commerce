#!/bin/sh
set -eu
cd shop/apps/backend/.medusa/server
../../../../node_modules/.bin/medusa db:migrate
exec ../../../../node_modules/.bin/medusa start --host 0.0.0.0 --port "${PORT:-9000}"
