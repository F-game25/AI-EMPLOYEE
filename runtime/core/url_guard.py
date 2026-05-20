"""URL safety guard — single source of truth for SSRF protection.

Used by:
- CloakBrowser (research fetches)
- learning_orchestrator.execute_learning (selected_urls)
- auto_research_agent (search-discovered URLs before navigation)
- webhook test endpoints
- any future user-URL ingestion path

Rejects: non-http(s) schemes, loopback, RFC1918 private, link-local
(incl. cloud metadata 169.254.0.0/16), unique-local IPv6, this-network.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.parse as _up
from typing import Optional


_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),     # IPv4 loopback
    ipaddress.ip_network("::1/128"),         # IPv6 loopback
    ipaddress.ip_network("10.0.0.0/8"),      # RFC1918 private
    ipaddress.ip_network("172.16.0.0/12"),   # RFC1918 private
    ipaddress.ip_network("192.168.0.0/16"),  # RFC1918 private
    ipaddress.ip_network("169.254.0.0/16"),  # link-local (incl AWS/GCP/Azure metadata)
    ipaddress.ip_network("fc00::/7"),        # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
    ipaddress.ip_network("0.0.0.0/8"),       # this-network
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT (often used for internal services)
]

# Allow override for explicit internal-mode operation (e.g. testing locally)
import os
_ALLOW_PRIVATE = os.getenv("URLGUARD_ALLOW_PRIVATE", "").strip().lower() in ("1", "true", "yes")


class UnsafeURLError(ValueError):
    """Raised when a URL fails SSRF safety checks."""


def validate_url(url: str) -> Optional[str]:
    """Returns None if URL is safe to fetch, or an error string if rejected.

    Cheap to call (single DNS resolution; cached by libc). Caller should reject
    the request entirely when this returns a string.
    """
    if not url or not isinstance(url, str):
        return "URL is empty or not a string"

    try:
        parsed = _up.urlparse(url)
    except Exception as e:
        return f"URL parse failed: {e}"

    if parsed.scheme not in ("http", "https"):
        return f"URL scheme '{parsed.scheme}' not allowed; only http/https"

    hostname = parsed.hostname
    if not hostname:
        return "URL has no hostname"

    # Reject literal IPs that themselves match blocked ranges (before DNS)
    try:
        literal = ipaddress.ip_address(hostname)
        if not _ALLOW_PRIVATE:
            for net in _BLOCKED_NETWORKS:
                if literal in net:
                    return f"URL targets blocked network {net}"
        return None
    except ValueError:
        pass  # not a literal IP; resolve via DNS

    # DNS resolve and check every returned address
    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return f"URL hostname could not be resolved: {hostname}"

    if _ALLOW_PRIVATE:
        return None

    for _family, _socktype, _proto, _canonname, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return f"resolved address is not a valid IP: {ip_str}"
        for net in _BLOCKED_NETWORKS:
            if ip in net:
                return (
                    f"URL '{hostname}' resolves to a private/reserved address "
                    f"({ip_str} in {net}); SSRF blocked"
                )

    return None


def require_safe_url(url: str) -> None:
    """Raise UnsafeURLError if the URL fails SSRF checks. No return value."""
    err = validate_url(url)
    if err is not None:
        raise UnsafeURLError(err)
