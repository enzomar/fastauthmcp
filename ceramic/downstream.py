"""Authenticated downstream client utilities.

Provides pre-configured HTTP and SOAP clients that automatically inject
the current request's access token. These are convenience wrappers for
tool code that needs to call downstream APIs on behalf of the authenticated user.

Usage in tools:

    from ceramic.downstream import authenticated_client, authenticated_soap_client

    @mcp.tool()
    def get_orders() -> list:
        client = authenticated_client()
        resp = client.get("https://api.internal.com/orders")
        return resp.json()

    @mcp.tool()
    def get_invoice(invoice_id: str) -> dict:
        soap = authenticated_soap_client("https://legacy.internal.com/InvoiceService?wsdl")
        return soap.service.GetInvoice(invoice_id)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ceramic.identity import _access_token_var

logger = logging.getLogger(__name__)


def authenticated_client(
    *,
    base_url: str = "",
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> httpx.Client:
    """Create a synchronous httpx client with the current user's Bearer token.

    The token is injected into the Authorization header automatically.
    Call this inside a tool function after authentication has completed.

    Args:
        base_url: Optional base URL for all requests.
        timeout: Request timeout in seconds (default 30).
        headers: Additional headers to include in all requests.

    Returns:
        An httpx.Client pre-configured with the Bearer token.

    Raises:
        RuntimeError: If called outside an authenticated request context.
    """
    token = _access_token_var.get(None)
    if token is None:
        raise RuntimeError(
            "authenticated_client() called outside an authenticated request context. "
            "Ensure the auth middleware has run before your tool code executes."
        )

    all_headers = {"Authorization": f"Bearer {token}"}
    if headers:
        all_headers.update(headers)

    return httpx.Client(
        base_url=base_url,
        timeout=timeout,
        headers=all_headers,
    )


def authenticated_async_client(
    *,
    base_url: str = "",
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """Create an async httpx client with the current user's Bearer token.

    Same as authenticated_client() but returns an async-compatible client.

    Args:
        base_url: Optional base URL for all requests.
        timeout: Request timeout in seconds (default 30).
        headers: Additional headers to include in all requests.

    Returns:
        An httpx.AsyncClient pre-configured with the Bearer token.

    Raises:
        RuntimeError: If called outside an authenticated request context.
    """
    token = _access_token_var.get(None)
    if token is None:
        raise RuntimeError(
            "authenticated_async_client() called outside an authenticated request context."
        )

    all_headers = {"Authorization": f"Bearer {token}"}
    if headers:
        all_headers.update(headers)

    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        headers=all_headers,
    )


def authenticated_soap_client(
    wsdl_url: str,
    *,
    service_name: str | None = None,
    port_name: str | None = None,
    timeout: float = 30.0,
    token_header: str = "Authorization",
    token_prefix: str = "Bearer",
) -> Any:
    """Create a SOAP client with the current user's token on the HTTP transport.

    Uses the ``zeep`` library (included as a core dependency).
    The token is injected as an HTTP header on the transport layer, not in the
    SOAP envelope. This is the most common pattern for OAuth2-protected SOAP services.

    For WS-Security token injection into the SOAP envelope, use
    ``authenticated_soap_client_wsse()`` instead.

    Args:
        wsdl_url: URL or path to the WSDL file.
        service_name: SOAP service name (if WSDL defines multiple).
        port_name: SOAP port name (if service has multiple ports).
        timeout: HTTP transport timeout in seconds.
        token_header: HTTP header name for the token (default "Authorization").
        token_prefix: Prefix before the token value (default "Bearer").

    Returns:
        A zeep.Client configured with authenticated transport.

    Raises:
        RuntimeError: If called outside an authenticated request context.
        ImportError: If zeep is not installed.
    """
    token = _access_token_var.get(None)
    if token is None:
        raise RuntimeError(
            "authenticated_soap_client() called outside an authenticated request context."
        )

    try:
        from zeep import Client
        from zeep.transports import Transport
    except ImportError as exc:
        raise ImportError(
            "SOAP support requires the 'zeep' package. "
            "Install it with: pip install zeep"
        ) from exc

    # Create an httpx-based session with the auth header
    session = httpx.Client(
        timeout=timeout,
        headers={token_header: f"{token_prefix} {token}"},
    )
    transport = Transport(session=session)

    kwargs: dict[str, Any] = {}
    if service_name:
        kwargs["service_name"] = service_name
    if port_name:
        kwargs["port_name"] = port_name

    return Client(wsdl_url, transport=transport, **kwargs)


def authenticated_soap_client_wsse(
    wsdl_url: str,
    *,
    service_name: str | None = None,
    port_name: str | None = None,
    timeout: float = 30.0,
    token_type: str = "http://docs.oasis-open.org/wss/oasis-wss-saml-token-profile-1.1#SAMLV2.0",
) -> Any:
    """Create a SOAP client with the token in the WS-Security SOAP header.

    Injects the access token as a BinarySecurityToken in the SOAP envelope's
    WS-Security header. Use this for services that expect the token in the
    SOAP message rather than as an HTTP header.

    Args:
        wsdl_url: URL or path to the WSDL file.
        service_name: SOAP service name (if WSDL defines multiple).
        port_name: SOAP port name (if service has multiple ports).
        timeout: HTTP transport timeout in seconds.
        token_type: WS-Security token type URI.

    Returns:
        A zeep.Client configured with WS-Security token injection.

    Raises:
        RuntimeError: If called outside an authenticated request context.
        ImportError: If zeep is not installed.
    """
    token = _access_token_var.get(None)
    if token is None:
        raise RuntimeError(
            "authenticated_soap_client_wsse() called outside an authenticated request context."
        )

    try:
        from zeep import Client
        from zeep.transports import Transport
    except ImportError as exc:
        raise ImportError(
            "SOAP WS-Security support requires the 'zeep' package. "
            "Install it with: pip install zeep"
        ) from exc

    from lxml import etree

    # Build the WS-Security header with BinarySecurityToken
    class _BearerTokenPlugin:
        """Zeep plugin that injects a BinarySecurityToken into the SOAP header."""

        def __init__(self, access_token: str, token_type_uri: str) -> None:
            self._token = access_token
            self._token_type = token_type_uri

        def egress(
            self,
            envelope: Any,
            http_headers: dict,
            operation: Any,
            binding_options: Any,
        ) -> Any:
            """Inject WS-Security header before sending."""
            WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
            header = envelope.find(f"{{{etree.QName(envelope).namespace}}}Header")
            if header is None:
                header = etree.SubElement(
                    envelope, f"{{{etree.QName(envelope).namespace}}}Header"
                )

            security = etree.SubElement(header, f"{{{WSSE_NS}}}Security")
            bst = etree.SubElement(security, f"{{{WSSE_NS}}}BinarySecurityToken")
            bst.set("ValueType", self._token_type)
            bst.set(
                "EncodingType",
                "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary",
            )
            bst.text = self._token

            return envelope, http_headers

    session = httpx.Client(timeout=timeout)
    transport = Transport(session=session)

    kwargs: dict[str, Any] = {"plugins": [_BearerTokenPlugin(token, token_type)]}
    if service_name:
        kwargs["service_name"] = service_name
    if port_name:
        kwargs["port_name"] = port_name

    return Client(wsdl_url, transport=transport, **kwargs)
