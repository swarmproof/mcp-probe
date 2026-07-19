#!/usr/bin/env bash
# mcp-probe demo — the two things no other tool shows in a CI gate:
#   (1) the toolset token number, (2) the disambiguation matrix.
#
# Record a GIF with:  asciinema rec demo.cast -c "bash scripts/demo.sh" && agg demo.cast demo.gif
# Requires: mcp-probe installed; PY = a python with the MCP SDK; Ollama for the matrix step.
set -euo pipefail

PY="${PY:-python}"
S="tests/servers"
pause() { sleep "${1:-2}"; }
say() { printf '\n\033[1;38;5;52m$ %s\033[0m\n' "$*"; }

say "mcp-probe run \"$PY $S/good_server.py\""
mcp-probe run "$PY $S/good_server.py" 2>/dev/null; pause 3

say "# a bloated toolset — watch the token tax every agent pays"
say "mcp-probe run \"$PY $S/bloated_server.py\" --fail-under B"
mcp-probe run "$PY $S/bloated_server.py" --fail-under B 2>/dev/null || echo "exit $? — gate failed (as it should)"; pause 4

say "# the headline: which tools do agents confuse? (needs a local model)"
say "mcp-probe run \"$PY $S/confusable_server.py\" --legibility --model ollama:mistral-small:latest --allow-writes"
if curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
  mcp-probe run "$PY $S/confusable_server.py" --legibility \
    --model "${MCP_PROBE_LIVE_MODEL:-ollama:mistral-small:latest}" --allow-writes 2>/dev/null
else
  echo "(skipped — Ollama not running on :11434)"
fi
pause 4

say "# CI gate + badge, in one line"
say "mcp-probe run \"$PY $S/good_server.py\" --fail-under B && mcp-probe badge --from <report>.json"
echo "✓ mcp-probe: A"
