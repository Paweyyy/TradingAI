#!/usr/bin/env bash
# Thin wrapper around the tradingai CLI for the analysis skill.
# Locates the repo root, activates the venv if present, and forwards args.
# READ-ONLY by intent: do not use for `tick`/`run` (those place live orders).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$ROOT"

# Activate a local virtualenv if one exists (best effort).
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Default to demo; never silently touch live from analysis.
export KRAKEN_DEMO="${KRAKEN_DEMO:-true}"
# Allow running without an editable install.
export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"

exec python3 -m tradingai.runner "$@"
