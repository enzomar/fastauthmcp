# FastAuthMCP Demo — fastauthmcp login → tool call
Output docs/demo.gif
Set FontSize 14
Set Width 800
Set Height 500
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 40ms

Type "# Secure your FastMCP server with FastAuthMCP"
Enter
Sleep 1s

Type "pip install fastauthmcp"
Enter
Sleep 2s

Type ""
Enter

Type "# One import change — that's it"
Enter
Sleep 500ms

Type 'cat server.py | head -5'
Enter
Sleep 1.5s

Type ""
Enter

Type "# Authenticate with your identity provider"
Enter
Sleep 500ms

Type "fastauthmcp login"
Enter
Sleep 3s

Type ""
Enter

Type "# Check who you are"
Enter
Sleep 500ms

Type "fastauthmcp whoami"
Enter
Sleep 2s

Type ""
Enter

Type "# Run the server — fully authenticated"
Enter
Sleep 500ms

Type "fastauthmcp run"
Enter
Sleep 2s

Type ""
Enter
Sleep 1s

Type "# ✓ Every tool call is now authenticated, authorized, and traced"
Enter
Sleep 3s
