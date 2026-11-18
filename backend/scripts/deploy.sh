#!/usr/bin/env bash
# Build, precompile bytecode, deploy:  scripts/deploy.sh [dev|prod]
#
# Lambda's code directory is read-only, so a plain `sam build && sam deploy`
# ships no .pyc files and Python recompiles every module (fastapi, pydantic,
# boto3, ...) on each cold start — measured as ~60% of the API's import time.
# checked-hash pycs stay valid however the zip treats mtimes, and fall back to
# compiling if a source ever changes without a rebuild.
set -euo pipefail
cd "$(dirname "$0")/.."

env="${1:-dev}"
python="${PYTHON:-/opt/homebrew/bin/python3.12}"  # must match the Lambda runtime

"$python" -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version'
sam build
for fn in .aws-sam/build/*/; do
  [ -f "$fn/app/main.py" ] || continue
  "$python" -m compileall -q -j 0 --invalidation-mode checked-hash "$fn" >/dev/null
done
sam deploy --config-env "$env"
