#!/usr/bin/env bash
# Refresh the bundled Public Suffix List (MPL-2.0, see NOTICE).
set -euo pipefail
cd "$(dirname "$0")/.."
curl -fsSL https://publicsuffix.org/list/public_suffix_list.dat \
  -o engine/src/mcp_privacy_guard/data/public_suffix_list.dat
