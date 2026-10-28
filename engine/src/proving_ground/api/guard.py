"""Refuse requests that did not come from this machine's browser."""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

LOCAL_NAMES = {"127.0.0.1", "localhost", "::1"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def host_name(host: str) -> str:
    """'127.0.0.1:7357' -> '127.0.0.1', '[::1]:7357' -> '::1'."""
    try:
        return urlsplit(f"http://{host}").hostname or ""
    except ValueError:
        return ""


def refusal(request: Request) -> JSONResponse | None:
    """A 403 for a foreign Host (DNS rebinding) or a write without a local Origin (CSRF)."""
    if host_name(request.headers.get("host", "")) not in LOCAL_NAMES:
        return JSONResponse({"detail": "Rig only answers on localhost."}, 403)
    if request.method not in SAFE_METHODS:
        origin = urlsplit(request.headers.get("origin", ""))
        if origin.scheme != "http" or origin.hostname not in LOCAL_NAMES:
            return JSONResponse({"detail": "Writes must come from the local app."}, 403)
    return None
