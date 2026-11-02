# VHS tape for the README hero GIF — renders docs/assets/demo.gif
# Render from the repo root with:  vhs docs/demo.tape
# Reproducible by design: it grades the `lying_server` fixture (a server whose
# `delete_record` tool declares readOnlyHint=true), so the Safety hard-gate fires
# the same way every run — no model, no network beyond the local server.

Output docs/assets/demo.gif

Set Shell bash
Set FontSize 15
Set Width 1240
Set Height 700
Set Padding 28
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms
Set WindowBar Colorful
Set WindowBarSize 36

# --- off-camera setup: put the venv on PATH, stage the fixture under a natural name ---
Hide
Type "export PATH=/Users/marouaboudoukha/Projects/personal/ventures-studio/Git-repos/ai-agents/agent-reliability/mcp-probe/.venv/bin:$PATH"
Enter
Type "mkdir -p /tmp/mcpq-demo && cp /Users/marouaboudoukha/Projects/personal/ventures-studio/Git-repos/ai-agents/agent-reliability/mcp-probe/tests/servers/lying_server.py /tmp/mcpq-demo/records_server.py && cd /tmp/mcpq-demo"
Enter
Type "clear"
Enter
Show

# --- on camera: one command, the whole story ---
Sleep 600ms
Type "mcp-quality run 'python records_server.py' --safety --fail-under B 2>/dev/null"
Sleep 800ms
Enter
Sleep 7s
