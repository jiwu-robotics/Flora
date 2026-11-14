#!/usr/bin/env bash
# Bootstrap the upstream Docker Compose self-host deployment.
set -euo pipefail

readonly REPOSITORY_URL="https://github.com/multica-ai/multica.git"

usage() {
  cat <<'EOF'
Usage: deploy.sh [options]

Clone the latest stable Multica release and start its official Docker Compose
self-host deployment on loopback. Add the packaged Caddy overlay only after
reviewing the selected private or public exposure plan.

Options:
  --directory <path>     New destination; defaults to /opt/app/multica.
  --ref <release-tag>    Concrete upstream release tag; defaults to latest stable vX.Y.Z.
  --image-tag <tag>      Published image tag; defaults to the resolved --ref.
  --backend-port <port>  Loopback backend port; defaults to 8080.
  --frontend-port <port> Loopback frontend port; defaults to 3000.
  -h, --help             Show this help text.

The bootstrap creates <install-directory>/.env when absent, generates its
secrets, invokes the upstream `make selfhost` target with the selected release
image tag, and verifies /readyz. It never publishes the service on 0.0.0.0.
EOF
}

fail() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

latest_stable_release() {
  git ls-remote --tags --refs "$REPOSITORY_URL" 'refs/tags/v*' |
    python3 -c '
import re
import sys

tags = (line.rsplit("/", 1)[-1].strip() for line in sys.stdin if "\t" in line)
stable = [tag for tag in tags if re.fullmatch(r"v\d+\.\d+\.\d+", tag)]
if not stable:
    raise SystemExit("no stable vX.Y.Z release tag found")
print(max(stable, key=lambda tag: tuple(map(int, tag[1:].split(".")))))
'

}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}
initialize_env() {
  [[ -f .env ]] && return

  cp .env.example .env
  jwt_secret="$(openssl rand -hex 32)"
  postgres_password="$(openssl rand -hex 24)"
  vcs_secret_key="$(openssl rand -base64 32)"

  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "s/^JWT_SECRET=.*/JWT_SECRET=$jwt_secret/" .env
    sed -i '' "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$postgres_password/" .env
    sed -i '' -E "s#^(DATABASE_URL=postgres://[^:]+:)[^@]*(@.*)#\1$postgres_password\2#" .env
    sed -i '' "s#^MULTICA_VCS_SECRET_KEY=.*#MULTICA_VCS_SECRET_KEY=$vcs_secret_key#" .env
  else
    sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$jwt_secret/" .env
    sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$postgres_password/" .env
    sed -i -E "s#^(DATABASE_URL=postgres://[^:]+:)[^@]*(@.*)#\1$postgres_password\2#" .env
    sed -i "s#^MULTICA_VCS_SECRET_KEY=.*#MULTICA_VCS_SECRET_KEY=$vcs_secret_key#" .env
  fi
}

install_dir="/opt/app/multica"
revision=""
image_tag=""
backend_port="8080"
frontend_port="3000"

while (($#)); do
  case "$1" in
    --directory)
      (($# >= 2)) || fail "--directory requires a path"
      install_dir="$2"
      shift 2
      ;;
    --ref)
      (($# >= 2)) || fail "--ref requires a concrete release tag"
      revision="$2"
      shift 2
      ;;
    --image-tag)
      (($# >= 2)) || fail "--image-tag requires a tag"
      image_tag="$2"
      shift 2
      ;;
    --backend-port)
      (($# >= 2)) || fail "--backend-port requires a port"
      backend_port="$2"
      shift 2
      ;;
    --frontend-port)
      (($# >= 2)) || fail "--frontend-port requires a port"
      frontend_port="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done


require_command docker
require_command git
require_command make
require_command curl
require_command openssl
require_command python3

case "$revision" in
  "")
    revision="$(latest_stable_release)"
    ;;
  v[0-9]*)
    ;;
  *)
    fail "--ref must be a concrete v* release tag, not $revision"
    ;;
esac
[[ -n "$image_tag" ]] || image_tag="$revision"

docker info >/dev/null || fail "Docker daemon is not available"
compose_version="$(docker compose version --short 2>/dev/null)" \
  || fail "Docker Compose v2 is required; legacy docker-compose v1 is unsupported"
case "$compose_version" in
  1.*|v1.*)
    fail "Docker Compose v2 is required; found $compose_version"
    ;;
esac

if [[ -e "$install_dir" ]]; then
  fail "installation directory already exists: $install_dir"
fi

mkdir -p "$(dirname "$install_dir")"
git clone --depth 1 --branch "$revision" "$REPOSITORY_URL" "$install_dir"
(
  cd "$install_dir"
  actual_tag="$(git describe --tags --exact-match HEAD 2>/dev/null || true)"
  [[ "$actual_tag" == "$revision" ]] || \
    fail "requested release tag $revision was not checked out exactly"
  initialize_env

  # Keep upstream clone and image-pull proxy behavior, but bypass proxies for
  # loopback readiness probes.
  export NO_PROXY="${NO_PROXY:+$NO_PROXY,}localhost,127.0.0.1,::1"
  export no_proxy="${no_proxy:+$no_proxy,}localhost,127.0.0.1,::1"
  export PORT="$backend_port"
  export FRONTEND_PORT="$frontend_port"
  export MULTICA_IMAGE_TAG="$image_tag"

  make selfhost
  curl --fail --silent --show-error "http://localhost:${backend_port}/readyz"
  printf '\nMultica release %s (%s) is ready at http://localhost:%s\n' \
    "$revision" "$(git rev-parse HEAD)" "$frontend_port"
)
