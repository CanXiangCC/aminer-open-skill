"""Gateway auth headers for the two production extraction APIs.

The online gateway (datacenter.aminer.cn/gateway/open_platform) authenticates
``POST /extraction/bert/filter/batch`` and ``POST /extraction/v1/chat/completions``
with an AMiner open-platform token. The local GPU service ignores these
headers, so they are always sent when a token is configured — one code path
serves both local and online endpoints.

Token resolution: ``AMINER_API_KEY`` (preferred, same variable as the other
AMiner skills) with ``OPEN_PLATFORM_TOKEN`` accepted as a deprecated fallback.
Values are never logged.
"""

from __future__ import annotations

import os
from typing import Any

# Sent verbatim alongside Authorization; the open platform expects this tag.
X_PLATFORM = "openclaw"


def resolve_api_token() -> str:
    """Return the configured token, or "" when none is set. Never logs it."""
    return (os.environ.get("AMINER_API_KEY") or os.environ.get("OPEN_PLATFORM_TOKEN") or "").strip()


def gateway_headers(extra: dict[str, Any] | None = None) -> dict[str, str]:
    """Auth headers for the two extraction APIs; harmless when sent locally.

    ``Authorization`` uses the Bearer scheme; without a configured token only
    X-Platform (plus any ``extra``) is returned so local runs keep working.
    """
    headers: dict[str, str] = {"X-Platform": X_PLATFORM}
    token = resolve_api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra:
        headers.update(extra)
    return headers
