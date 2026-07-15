"""Local HTTP callback server for OAuth2 authorization code flow.

Receives the OAuth2 redirect callback on localhost and extracts the
authorization code and state parameter.
"""

from __future__ import annotations

import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

from fastauthmcp.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for the OAuth2 callback."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        logger.info("Callback server received request: %s", self.path)
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            result = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
            self.server._callback_result = result  # type: ignore[attr-defined]
            logger.info("Callback received with keys: %s", list(result.keys()))

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_SUCCESS_HTML)
        else:
            logger.warning("Callback server got unexpected path: %s", parsed.path)
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        """Log callback server requests at debug level."""
        logger.debug("Callback server: " + format, *args)


class CallbackServer:
    """Local HTTP server that listens for the OAuth2 callback.

    Starts a single-request HTTP server on localhost, waits for the IDP
    to redirect back with an authorization code, then shuts down.
    """

    def __init__(self) -> None:
        self._server: HTTPServer | None = None
        self._thread: Thread | None = None

    def start(self, port: int = 0) -> int:
        """Start the callback server. Returns the actual port number."""
        try:
            logger.debug("Attempting to start callback server on 127.0.0.1:%d", port)
            self._server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
            self._server.allow_reuse_address = True
            self._server._callback_result = None  # type: ignore[attr-defined]
            actual_port = self._server.server_address[1]
            self._thread = Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            logger.info(
                "Callback server started on 127.0.0.1:%d (thread=%s)",
                actual_port,
                self._thread.name,
            )
            return actual_port
        except OSError as exc:
            logger.error("Failed to start callback server on port %d: %s", port, exc)
            raise AuthenticationError(
                f"Failed to start callback server on port {port}: {exc}"
            ) from exc

    def wait_for_callback(self, timeout: float) -> dict[str, Any]:
        """Block until the callback arrives or timeout.

        Args:
            timeout: Maximum seconds to wait for the callback.

        Returns:
            Dict of query parameters from the callback URL.

        Raises:
            TimeoutError: If no callback arrives within the timeout.
        """
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server and self._server._callback_result is not None:  # type: ignore[attr-defined]
                result = self._server._callback_result  # type: ignore[attr-defined]
                # Don't shutdown here — the server thread may still be writing
                # the response to the browser. Caller is responsible for shutdown.
                return result
            time.sleep(0.1)
        raise TimeoutError(f"Callback not received within {timeout} seconds")

    def shutdown(self) -> None:
        """Shut down the callback server and free the port."""
        if self._server:
            # Run shutdown in a separate thread to avoid blocking if
            # serve_forever is stuck handling a request (e.g. /favicon.ico).
            import threading

            server = self._server
            self._server = None

            def _do_shutdown():
                try:
                    server.shutdown()
                except Exception:
                    pass

            t = threading.Thread(target=_do_shutdown, daemon=True)
            t.start()
            t.join(timeout=2)
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None


# ---------------------------------------------------------------------------
# Success page HTML (shown after OAuth callback)
# ---------------------------------------------------------------------------

_SUCCESS_HTML = (
    b"<!DOCTYPE html><html><head><meta charset='utf-8'>"
    b"<style>"
    b"*{margin:0;padding:0;box-sizing:border-box}"
    b"body{font-family:'Inter',system-ui,sans-serif;background:#050709;color:#e7e9ee;"
    b"display:flex;align-items:center;justify-content:center;min-height:100vh;"
    b"text-align:center;padding:2rem}"
    b".card{max-width:400px}"
    b".logo{display:inline-flex;align-items:center;justify-content:center;"
    b"width:48px;height:48px;border-radius:12px;"
    b"background:linear-gradient(135deg,#22d3ee,#8b5cf6);margin-bottom:1.5rem}"
    b".logo span{width:14px;height:14px;border-radius:4px;background:#050709}"
    b"h1{font-size:1.5rem;font-weight:700;margin-bottom:0.75rem}"
    b"p{color:rgba(231,233,238,0.6);font-size:0.95rem;line-height:1.5}"
    b".status{margin-top:1.5rem;font-size:0.8rem;color:rgba(231,233,238,0.4)}"
    b"</style></head><body>"
    b"<div class='card'>"
    b"<div class='logo'><span></span></div>"
    b"<h1>&#x2705; Authentication Successful</h1>"
    b"<p>You are now logged in. Return to your terminal to continue.</p>"
    b"<p class='status' id='status'>This tab will close automatically&hellip;</p>"
    b"</div>"
    b"<script>"
    b"(function(){"
    b"try{window.close()}catch(e){}"
    b"setTimeout(function(){"
    b"try{window.close()}catch(e){}"
    b"setTimeout(function(){"
    b"document.getElementById('status').textContent="
    b"'You can safely close this tab now.';"
    b"},1500);"
    b"},1000);"
    b"})();"
    b"</script>"
    b"</body></html>"
)
