# FastAuthMCP Demo GIF
# Record with: vhs docs/demo.tape
#
# Before recording, run:
#   ./scripts/setup-demo-recording.sh
#
# This creates /tmp/fastauthmcp-recording/ with a venv and mock outputs
# so the recording is deterministic and doesn't need network access.

Output docs/demo.gif
Set FontSize 14
Set Width 900
Set Height 550
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 45ms
Set Shell "bash"
Set Env "PATH" "/tmp/fastauthmcp-recording/venv/bin:/usr/bin:/bin"
Set Env "HOME" "/tmp/fastauthmcp-recording"
Set Env "PS1" "\[\e[36m\]fastauthmcp\[\e[0m\] $ "
Set WorkingDirectory "/tmp/fastauthmcp-recording/project"

# --- Title ---
Sleep 500ms
Type "# FastAuthMCP: Add enterprise auth to any MCP server in 30 seconds"
Enter
Sleep 2s

# --- Show server code ---
Type "cat server.py"
Enter
Sleep 3.5s

Type ""
Enter
Sleep 500ms

# --- Show config ---
Type "cat fastauthmcp.yaml"
Enter
Sleep 3.5s

Type ""
Enter
Sleep 500ms

# --- Validate ---
Type "fastauthmcp doctor"
Enter
Sleep 3s

Type ""
Enter
Sleep 500ms

# --- Login ---
Type "fastauthmcp login"
Enter
Sleep 4s

Type ""
Enter
Sleep 500ms

# --- Whoami ---
Type "fastauthmcp whoami"
Enter
Sleep 3s

Type ""
Enter
Sleep 500ms

# --- Run ---
Type "# Server ready — every tool call is now authenticated"
Enter
Sleep 1s

Type "fastauthmcp run --transport stdio"
Enter
Sleep 3s

# Ctrl+C to stop
Ctrl+C
Sleep 1s

Type ""
Enter
Type "# Zero code changes. One import. One config file."
Enter
Sleep 4s
