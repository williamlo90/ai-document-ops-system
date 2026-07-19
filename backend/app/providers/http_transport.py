from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.providers.contracts import ProviderError


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_json_without_redirects(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    timeout_seconds: int,
    provider_name: str,
    http_error_code: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    opener = urllib.request.build_opener(RejectRedirects())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise ProviderError(
            http_error_code,
            provider_name,
            retryable=exc.code == 429 or exc.code >= 500,
        ) from exc
