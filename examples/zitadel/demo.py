"""Ceramic Demo: Chat UI with AI tool calling via Ceramic + Zitadel.

Starts two services:
1. The Ceramic MCP server (SSE transport) with Zitadel authentication
2. A simple HTTP server serving a chat web UI

The chat UI emulates an AI assistant that calls MCP tools through Ceramic.
On startup, if no valid session exists, the browser opens for OAuth2 login.
Once authenticated, all tool calls go through the full middleware pipeline
(auth, authz, observability, sessions).

Usage:
    python demo.py

Then open http://localhost:3000 in your browser (opens automatically).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# Add project root to path for development
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from server import mcp

# --- Configuration ---
WEB_PORT = int(os.environ.get("DEMO_WEB_PORT", "3000"))
MCP_PORT = int(os.environ.get("DEMO_MCP_PORT", "8000"))
MCP_HOST = os.environ.get("DEMO_MCP_HOST", "localhost")

# Path to the chat HTML file
CHAT_HTML = Path(__file__).parent / "demo_chat.html"


# --- Shared event loop for the demo ---
# We use a single persistent event loop in a background thread so that
# contextvar state (identity) persists across tool calls within the same
# session, and the OAuth flow's callback server doesn't conflict with
# the web UI's synchronous HTTP handler.

_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None


def _start_event_loop() -> asyncio.AbstractEventLoop:
    """Start a persistent background event loop for pipeline execution."""
    global _loop, _loop_thread
    _loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(_loop)
        _loop.run_forever()

    _loop_thread = threading.Thread(target=_run, daemon=True)
    _loop_thread.start()
    return _loop


def _run_in_loop(coro):
    """Submit a coroutine to the persistent event loop and wait for the result."""
    assert _loop is not None
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=180)  # 3 min timeout for OAuth flows


# --- Simple AI "brain" that decides which tool to call ---

TOOL_DISPATCH = {
    "list projects": ("get_projects", {}),
    "show projects": ("get_projects", {}),
    "get projects": ("get_projects", {}),
    "projects": ("get_projects", {}),
    "who am i": ("whoami", {}),
    "whoami": ("whoami", {}),
    "hello": ("whoami", {}),
    "hi": ("whoami", {}),
    "hey": ("whoami", {}),
    "audit": ("get_audit_log", {"limit": 10}),
    "audit log": ("get_audit_log", {"limit": 10}),
    "history": ("get_audit_log", {"limit": 10}),
}


def ai_decide_tool(user_message: str) -> tuple[str, dict]:
    """Decide which tool to call based on user input.

    Always returns a tool — defaults to 'whoami' for unrecognized input,
    ensuring the auth pipeline always runs.
    """
    msg = user_message.lower().strip()

    # Direct dispatch
    for trigger, (tool, args) in TOOL_DISPATCH.items():
        if trigger in msg:
            return tool, args

    # Pattern matching for parameterized tools
    if "create" in msg and "project" in msg:
        name = "New Project"
        desc = "Created via chat"
        original = user_message.strip()
        if '"' in original:
            parts = original.split('"')
            if len(parts) >= 2:
                name = parts[1]
            if len(parts) >= 4:
                desc = parts[3]
        elif "called" in msg:
            name = user_message.split("called", 1)[1].strip().rstrip(".")
        elif "named" in msg:
            name = user_message.split("named", 1)[1].strip().rstrip(".")
        return "create_project", {"name": name, "description": desc}

    if "delete" in msg and "project" in msg:
        for word in msg.split():
            if word.startswith("proj-"):
                return "delete_project", {"project_id": word.rstrip(".")}
        return "delete_project", {"project_id": "proj-001"}

    if ("details" in msg or "info" in msg) and "proj-" in msg:
        for word in msg.split():
            if word.startswith("proj-"):
                return "get_project_details", {"project_id": word.rstrip(".")}

    if "update" in msg and "status" in msg:
        project_id = "proj-001"
        status = "active"
        for word in msg.split():
            if word.startswith("proj-"):
                project_id = word.rstrip(".")
            if word in ("planning", "active", "paused", "completed", "archived"):
                status = word
        return "update_project_status", {"project_id": project_id, "status": status}

    # Default: any unrecognized message calls whoami (ensures auth runs)
    return "whoami", {}


# --- Tool execution through Ceramic pipeline ---

async def call_tool_via_ceramic(tool_name: str, args: dict):
    """Call a tool through Ceramic's full middleware pipeline.

    Uses the live MCP server instance with its configured middleware
    (auth, authz, observability, sessions). On first call, the auth
    middleware will trigger the browser-based OAuth2 flow.
    """
    from ceramic.middleware.pipeline import RequestContext
    import inspect

    # Build request context
    ctx = RequestContext(tool_name=tool_name)

    # Define the handler that actually executes the tool
    tool_func = mcp._tool_functions.get(tool_name)

    async def handler():
        if tool_func is None:
            return {"error": "tool_not_found", "message": f"Tool '{tool_name}' not found"}
        result = tool_func(**args)
        if inspect.isawaitable(result):
            return await result
        return result

    # Execute through the FULL Ceramic pipeline (auth, authz, observability, sessions)
    result = await mcp._pipeline.execute(ctx, handler)
    return result


# --- HTTP API handler for the chat UI ---

class DemoHandler(SimpleHTTPRequestHandler):
    """Serves the chat HTML and handles API requests for tool calling."""

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_chat_html()
        elif self.path == "/api/health":
            self._json_response({"status": "ok"})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/chat":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            user_message = data.get("message", "")
            self._handle_chat(user_message)
        else:
            self.send_error(404)

    def _handle_chat(self, user_message: str):
        """Process a chat message: AI decides tool, calls it via Ceramic, returns result."""
        tool_name, tool_args = ai_decide_tool(user_message)

        # Call the tool through Ceramic's middleware pipeline
        # Uses the persistent event loop so contextvar/token state is preserved.
        try:
            result = _run_in_loop(call_tool_via_ceramic(tool_name, tool_args))

            # Check if the result is an auth/error response from middleware
            if isinstance(result, dict) and "error" in result:
                error_type = result.get("error", "")
                if error_type in ("authentication_required", "authentication_failed"):
                    self._json_response({
                        "type": "auth_required",
                        "message": (
                            "Authentication required. A browser window should have opened "
                            "for login. Please complete the sign-in and try again."
                        ),
                    })
                elif error_type == "authorization_denied":
                    self._json_response({
                        "type": "tool_result",
                        "tool": tool_name,
                        "args": tool_args,
                        "result": {"error": "Access denied", "detail": result.get("message", "Insufficient permissions")},
                    })
                else:
                    self._json_response({
                        "type": "error",
                        "tool": tool_name,
                        "message": result.get("message", str(result)),
                    })
                return

            self._json_response({
                "type": "tool_result",
                "tool": tool_name,
                "args": tool_args,
                "result": result,
            })
        except Exception as exc:
            self._json_response({
                "type": "error",
                "tool": tool_name,
                "message": str(exc),
            })

    def _serve_chat_html(self):
        """Serve the chat UI HTML file."""
        if CHAT_HTML.exists():
            content = CHAT_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(500, "Chat HTML not found")

    def _json_response(self, data: dict, status: int = 200):
        """Send a JSON response."""
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Suppress default logging to keep output clean."""
        pass


def run_web_server():
    """Start the web UI HTTP server."""
    server = HTTPServer(("0.0.0.0", WEB_PORT), DemoHandler)
    server.serve_forever()


def ensure_authenticated():
    """Pre-authenticate on startup if no valid token exists.

    Triggers the OAuth2 flow immediately so the user is logged in
    before they start chatting. This provides a seamless experience.
    """
    print("  Checking authentication status...")
    try:
        result = _run_in_loop(call_tool_via_ceramic("whoami", {}))
        if isinstance(result, dict) and result.get("email"):
            print(f"  ✓ Authenticated as: {result['email']}")
            roles = result.get("roles", [])
            if roles:
                print(f"    Roles: {', '.join(roles)}")
            return True
        elif isinstance(result, dict) and result.get("error") == "authentication_required":
            print("  ⚠ Authentication required — browser should have opened for login.")
            print("    Complete the sign-in, then refresh the chat UI.")
            return False
        else:
            # Auth ran but identity is empty — might be a claim path issue
            print(f"  ⚠ Authenticated but identity details unavailable: {result}")
            return True
    except Exception as exc:
        print(f"  ⚠ Auth check failed: {exc}")
        return False


def main():
    print()
    print("┌──────────────────────────────────────────────────────────────┐")
    print("│            Ceramic Demo — Web Chat + MCP Server              │")
    print("├──────────────────────────────────────────────────────────────┤")
    print("│                                                              │")
    print("│  What's running:                                             │")
    print("│    • MCP server with Zitadel OIDC authentication             │")
    print("│    • Web chat UI that calls tools through the full pipeline  │")
    print("│                                                              │")
    print("│  Middleware pipeline (every tool call goes through):          │")
    print("│    Observability → Session → Authentication → Authorization  │")
    print("│                                                              │")
    print("│  Available tools (role-based access):                         │")
    print("│    whoami             — any authenticated user                │")
    print("│    get_projects       — requires 'viewer' role               │")
    print("│    get_project_details— requires 'viewer' role               │")
    print("│    create_project     — requires 'editor' role               │")
    print("│    update_project_status — requires 'editor' role            │")
    print("│    delete_project     — requires 'admin' role                │")
    print("│    get_audit_log      — requires 'admin' role                │")
    print("│                                                              │")
    print("│  Try saying in the chat:                                     │")
    print('│    "who am i"  "list projects"  "create project called X"    │')
    print('│    "audit log"  "delete project proj-001"                    │')
    print("│                                                              │")
    print("├──────────────────────────────────────────────────────────────┤")
    print(f"│  Chat UI:    http://localhost:{WEB_PORT:<39}│")
    print(f"│  MCP Server: http://{MCP_HOST}:{MCP_PORT} (SSE){' ' * (39 - len(f'{MCP_HOST}:{MCP_PORT} (SSE)'))}│")
    print("│  IDP:        Zitadel Cloud (ceramic-oss)                     │")
    print("└──────────────────────────────────────────────────────────────┘")
    print()

    # Start persistent event loop for pipeline execution
    _start_event_loop()

    # Pre-authenticate (triggers OAuth flow if needed)
    ensure_authenticated()
    print()

    # Start the web UI server in a thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print(f"  ✓ Web UI ready at http://localhost:{WEB_PORT}")

    # Auto-open the browser
    def _open_browser():
        import time
        time.sleep(1)
        webbrowser.open(f"http://localhost:{WEB_PORT}")

    browser_thread = threading.Thread(target=_open_browser, daemon=True)
    browser_thread.start()

    # Run the MCP server in the main thread (with SSE transport)
    print(f"  ✓ MCP server on http://{MCP_HOST}:{MCP_PORT} (SSE)")
    print()
    print("  Press Ctrl+C to stop.")
    print("=" * 60)
    print()
    try:
        mcp.run(transport="sse", host=MCP_HOST, port=MCP_PORT)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        sys.exit(0)


if __name__ == "__main__":
    main()
