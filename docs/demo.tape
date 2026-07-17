# FastAuthMCP Demo GIF
# Record with: vhs docs/demo.tape
#
# Before recording:
#   1. Run ./scripts/setup-demo-recording.sh
#   2. Login once: cd /tmp/fastauthmcp-recording/project && \
#      SSL_CERT_FILE=/tmp/combined-ca.pem \
#      /tmp/fastauthmcp-recording/venv/bin/fastauthmcp login
#   3. Then: cd /tmp/fastauthmcp-recording/project && vhs ~/devel/fastauthmcp/docs/demo.tape

Output "docs/demo.gif"
Set FontSize 14
Set Width 900
Set Height 550
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 45ms

# --- Setup: activate venv and set env ---
Hide
Type "export PATH=/tmp/fastauthmcp-recording/venv/bin:$PATH && export SSL_CERT_FILE=/tmp/combined-ca.pem && cd /tmp/fastauthmcp-recording/project && export PS1='$ '"
Enter
Sleep 2s
Show

# --- Title ---
Type "# FastAuthMCP: Enterprise auth for MCP servers in 30 seconds"
Enter
Sleep 2s

# --- Show server code ---
Type "cat server.py"
Enter
Sleep 4s

Type ""
Enter
Sleep 500ms

# --- Show config ---
Type "cat fastauthmcp.yaml"
Enter
Sleep 4s

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

# --- Whoami (shows logged-in user) ---
Type "fastauthmcp whoami"
Enter
Sleep 3s

Type ""
Enter
Sleep 500ms

# --- Conclusion ---
Type "# Zero code changes. One import. One YAML file. Production auth."
Enter
Sleep 4s
