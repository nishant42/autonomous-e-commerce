#!/usr/bin/env bash
# Bring up an open-source shop (storefront + back office) for the engine to drive.
#
# Nothing here is ours: Medusa provides the Next.js storefront customers browse,
# the admin dashboard, and the Admin API. We only read it.
#
#   backend + API     http://localhost:9000
#   admin dashboard   http://localhost:9000/app
#   storefront        http://localhost:8000
#
# Run it from the engine directory:  bash scripts/setup-medusa.sh
set -euo pipefail

SHOP_DIR="${SHOP_DIR:-$HOME/halden-shop}"
PG_CONTAINER="halden-postgres"
PG_PASSWORD="medusa"

say() { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
die() { printf "\n\033[31mFAILED: %s\033[0m\n" "$1" >&2; exit 1; }

say "1/4  Checking prerequisites"

command -v docker >/dev/null || die "Docker is not installed."
docker info >/dev/null 2>&1 || die "Docker Desktop is installed but not running. Start it, then re-run this script."

# Docker Desktop on macOS writes credsStore:"desktop" into ~/.docker/config.json,
# but its helper lives inside the app bundle and is often not on PATH. Without it
# even an anonymous pull of a public image fails with "error getting credentials".
DOCKER_DESKTOP_BIN="/Applications/Docker.app/Contents/Resources/bin"
if [ -x "$DOCKER_DESKTOP_BIN/docker-credential-desktop" ]; then
  export PATH="$DOCKER_DESKTOP_BIN:$PATH"
elif ! command -v docker-credential-desktop >/dev/null 2>&1; then
  # No helper anywhere: use a throwaway Docker config with no credsStore rather
  # than editing the user's own config.
  export DOCKER_CONFIG="${TMPDIR:-/tmp}/halden-docker-config"
  mkdir -p "$DOCKER_CONFIG"
  printf '{}' > "$DOCKER_CONFIG/config.json"
  echo "    docker creds      using a throwaway config (no credential helper found)"
fi
echo "    docker            ok"

NODE_MAJOR="$(node -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/' || echo 0)"
if [ "${NODE_MAJOR:-0}" -lt 22 ]; then
  echo "    node              $(node -v 2>/dev/null || echo none) - Medusa v2 needs 22 or newer"
  if command -v nvm >/dev/null 2>&1 || [ -s "$HOME/.nvm/nvm.sh" ]; then
    # shellcheck disable=SC1091
    . "$HOME/.nvm/nvm.sh"
    say "    installing Node 22 through nvm (this does not change your default)"
    nvm install 22
    nvm use 22
  else
    die "Install Node 22+ first:  nvm install 22 && nvm use 22"
  fi
fi
echo "    node              $(node -v)"

say "2/4  Starting Postgres in Docker"

# Macs often already run Postgres (Postgres.app serves 5432, 5433, 5434 at once),
# and on macOS a container can bind 0.0.0.0:PORT while another process holds
# 127.0.0.1:PORT - so connections silently reach the wrong server. Pick a port
# nothing answers on instead of assuming 5432 is ours.
pick_port() {
  for P in 5432 5433 5434 55432 55433 55434; do
    if ! nc -z 127.0.0.1 "$P" >/dev/null 2>&1; then echo "$P"; return; fi
  done
  die "no free port found for Postgres"
}

if docker ps -a --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
  docker start "$PG_CONTAINER" >/dev/null
  PG_PORT="$(docker port "$PG_CONTAINER" 5432 2>/dev/null | head -1 | sed 's/.*://')"
  echo "    reused existing container $PG_CONTAINER on port ${PG_PORT:-unknown}"
else
  PG_PORT="$(pick_port)"
  docker run -d --name "$PG_CONTAINER" \
    -e POSTGRES_PASSWORD="$PG_PASSWORD" -e POSTGRES_USER=medusa -e POSTGRES_DB=medusa \
    -p "${PG_PORT}:5432" postgres:16 >/dev/null
  echo "    started $PG_CONTAINER on port $PG_PORT"
fi

printf "    waiting for Postgres"
for _ in $(seq 1 40); do
  if docker exec "$PG_CONTAINER" pg_isready -U medusa >/dev/null 2>&1; then echo " ready"; break; fi
  printf "."; sleep 1
done

DB_URL="postgres://medusa:${PG_PASSWORD}@localhost:${PG_PORT}/medusa"
echo "    DATABASE_URL      $DB_URL"

say "3/4  Creating the Medusa shop in $SHOP_DIR"
if [ -d "$SHOP_DIR" ]; then
  echo "    $SHOP_DIR already exists, skipping creation"
else
  echo "    this downloads and builds the shop - expect several minutes"
  npx --yes create-medusa-app@latest "$(basename "$SHOP_DIR")" \
    --with-nextjs-starter \
    --db-url "$DB_URL" \
    --no-browser || die "create-medusa-app failed. Run it by hand in $(dirname "$SHOP_DIR") to see why."
fi

say "4/4  What to do next"
cat <<NEXT
    Start the shop (two terminals, from $SHOP_DIR):
      cd $SHOP_DIR && npm run dev            # backend + admin, port 9000
      cd $SHOP_DIR/.. && npm run dev         # storefront, port 8000  (path varies by version)

    Create an admin user if the installer did not:
      cd $SHOP_DIR && npx medusa user -e admin@medusajs.com -p supersecret

    If the installer ever asks for the database, use:
      $DB_URL

    Then point the engine at it:
      export MEDUSA_URL=http://localhost:9000
      export MEDUSA_EMAIL=admin@medusajs.com
      export MEDUSA_PASSWORD=supersecret
      cd <engine dir> && python3 run.py medusa check && python3 run.py medusa sync

    Leave the snapshot job running so availability history builds up:
      python3 run.py medusa watch 300
NEXT
