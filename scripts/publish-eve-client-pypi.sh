#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONOREPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
if [ -f "$MONOREPO_ROOT/packages/client/pyproject.toml" ]; then
  ROOT_DIR="$MONOREPO_ROOT"
  PACKAGE_DIR="$ROOT_DIR/packages/client"
else
  PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
  ROOT_DIR="$PACKAGE_DIR"
fi
DIST_DIR="${EVE_CLIENT_DIST_DIR:-$ROOT_DIR/dist}"
MODE="dry-run"
SKIP_BUILD="0"

usage() {
  cat <<'EOF'
Usage: publish-eve-client-pypi.sh [--dry-run|--publish] [--skip-build] [--dist-dir DIR]

Builds and validates eve-memory-client PyPI artifacts. --dry-run never uploads.
--publish uploads existing validated artifacts. In GitHub Actions it uses PyPI
Trusted Publishing when PYPI_API_TOKEN is absent; outside GitHub Actions it
requires PYPI_API_TOKEN.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --publish)
      MODE="publish"
      shift
      ;;
    --skip-build)
      SKIP_BUILD="1"
      shift
      ;;
    --dist-dir)
      if [ "$#" -lt 2 ]; then
        echo "--dist-dir requires a value" >&2
        exit 2
      fi
      DIST_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

mkdir -p "$DIST_DIR"

if [ "$SKIP_BUILD" != "1" ]; then
  rm -f "$DIST_DIR"/eve_memory_client-*.tar.gz "$DIST_DIR"/eve_memory_client-*-py3-none-any.whl
  uv build "$PACKAGE_DIR" --out-dir "$DIST_DIR"
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "python3 or python is required to validate release metadata" >&2
  exit 1
fi

shopt -s nullglob
SDISTS=("$DIST_DIR"/eve_memory_client-*.tar.gz)
WHEELS=("$DIST_DIR"/eve_memory_client-*-py3-none-any.whl)
EXTRA_ARTIFACTS=()
for candidate in "$DIST_DIR"/*; do
  [ -e "$candidate" ] || continue
  case "$(basename "$candidate")" in
    eve_memory_client-*.tar.gz|eve_memory_client-*-py3-none-any.whl)
      ;;
    *)
      EXTRA_ARTIFACTS+=("$candidate")
      ;;
  esac
done
shopt -u nullglob

if [ "${#SDISTS[@]}" -ne 1 ] || [ "${#WHEELS[@]}" -ne 1 ] || [ "${#EXTRA_ARTIFACTS[@]}" -ne 0 ]; then
  echo "Expected exactly one eve-memory-client sdist and one wheel in $DIST_DIR, with no extra files" >&2
  echo "Found sdists=${#SDISTS[@]} wheels=${#WHEELS[@]} extra=${#EXTRA_ARTIFACTS[@]}" >&2
  exit 1
fi

EXPECTED_VERSION="$(
  "$PYTHON_BIN" - "$PACKAGE_DIR/pyproject.toml" <<'PY'
import pathlib
import sys
import tomllib

data = tomllib.loads(pathlib.Path(sys.argv[1]).read_text())
print(data["project"]["version"])
PY
)"
EXPECTED_SDIST="eve_memory_client-${EXPECTED_VERSION}.tar.gz"
EXPECTED_WHEEL="eve_memory_client-${EXPECTED_VERSION}-py3-none-any.whl"
FOUND_SDIST="$(basename "${SDISTS[0]}")"
FOUND_WHEEL="$(basename "${WHEELS[0]}")"

if [ "$FOUND_SDIST" != "$EXPECTED_SDIST" ] || [ "$FOUND_WHEEL" != "$EXPECTED_WHEEL" ]; then
  echo "Expected artifact filenames to match pyproject version $EXPECTED_VERSION" >&2
  echo "Found sdist=$FOUND_SDIST wheel=$FOUND_WHEEL" >&2
  exit 1
fi

ARTIFACTS=("${SDISTS[@]}" "${WHEELS[@]}")

uvx twine check "${ARTIFACTS[@]}"

if [ "$MODE" = "publish" ]; then
  if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    if [ -n "${PYPI_API_TOKEN:-}" ]; then
      echo "Refusing PYPI_API_TOKEN in GitHub Actions; use PyPI Trusted Publishing" >&2
      exit 1
    fi
    uv publish --trusted-publishing always "${ARTIFACTS[@]}"
  elif [ -n "${PYPI_API_TOKEN:-}" ]; then
    UV_PUBLISH_TOKEN="$PYPI_API_TOKEN" uv publish "${ARTIFACTS[@]}"
  else
    echo "PYPI_API_TOKEN is required for --publish outside GitHub Actions trusted publishing" >&2
    exit 1
  fi
  echo "Published eve-memory-client artifacts from $DIST_DIR"
else
  echo "Dry run complete; not publishing eve-memory-client artifacts from $DIST_DIR"
fi
