# Ceramic Demo — ceramic login → tool call
Output docs/demo.gif
Set FontSize 14
Set Width 800
Set Height 500
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 40ms

Type "# Secure your FastMCP server with Ceramic"
Enter
Sleep 1s

Type "pip install ceramic-fwk"
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

Type "ceramic login"
Enter
Sleep 3s

Type ""
Enter

Type "# Check who you are"
Enter
Sleep 500ms

Type "ceramic whoami"
Enter
Sleep 2s

Type ""
Enter

Type "# Run the server — fully authenticated"
Enter
Sleep 500ms

Type "ceramic run"
Enter
Sleep 2s

Type ""
Enter
Sleep 1s

Type "# ✓ Every tool call is now authenticated, authorized, and traced"
Enter
Sleep 3s
