"""Production client for BERT ``POST /filter/batch``.

Calls the existing bert_service endpoint (server.py L234+) directly. Does NOT
touch bert_service or benchmark's stub ``BatchBertClient`` — pure HTTP client.

Contract (verified against bert_service/server.py + batch_run_split.filter_batch_papers;
proxied via datacenter-service /extraction/bert — EXTRACTION_GPU_API.md §1.1):
  request:  {papers:["<paper JSON str>", ...], threshold, batch_size}
            papers is []string: each element is a serialized
            {paper_id, sentences} object (proxy json.loads-escapes back to
            objects before forwarding to the GPU upstream).
  response: {papers:[{paper_id, kept, indices, confidences, total, kept_count}],
             paper_count, total_sentences, total_kept, inference_time_ms, batch_size}
  index alignment: per-paper local 0-based, aligned to the input sentences list
  (so callers MUST pass Stage-P's english_sentences, not origin-split combined).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests

from pipeline.benchmark.config import BERT_SERVER_URL, WF1_BERT_THRESHOLD
from pipeline.production.adapters.gateway_auth import gateway_headers

logger = logging.getLogger(__name__)

# Default per-request timeout (seconds). Mirrors llm_timeout default so BERT
# and LLM fail at the same horizon; overridable via yaml `bert_timeout`.
_DEFAULT_BERT_TIMEOUT = 30

# Default retry count for transient network errors (ConnectTimeout /
# ConnectionError). 2 retries => up to 3 total attempts. Overridable via yaml
# `bert_retries`. HTTP 4xx is NOT retried (caller bug, not transient).
_DEFAULT_BERT_RETRIES = 2

# Exponential backoff base (seconds): wait base*2^attempt between retries
# (5s, 10s for 2 retries).
_BACKOFF_BASE_SEC = 5.0


def filter_papers_batch(
    papers: list[dict[str, Any]],
    *,
    threshold: float = WF1_BERT_THRESHOLD,
    batch_size: int = 32,
    url: str = BERT_SERVER_URL,
    timeout: int = _DEFAULT_BERT_TIMEOUT,
    retries: int = _DEFAULT_BERT_RETRIES,
) -> dict[str, Any]:
    """POST /filter/batch and return the server response + client_elapsed_sec.

    Args:
        papers: ``[{paper_id, sentences: [str]}, ...]`` — sentences MUST be the
            Stage-P english_sentences (wash output), not origin-split combined.
        threshold: BERT keep threshold (top-level, applied to all papers).
        batch_size: server-side GPU mini-batch size.
        url: BERT server base URL.
        timeout: per-attempt request timeout seconds.
        retries: max retries on ConnectTimeout / ConnectionError (default 2).
            HTTP 4xx errors are NOT retried (raise immediately).

    Returns:
        Server response dict with ``client_elapsed_sec`` added.

    Raises:
        requests.HTTPError: on 4xx (no retry).
        requests.ConnectionError / ConnectTimeout / ReadTimeout: after all
            retries exhausted.
    """
    payload = {
        # Proxy contract (EXTRACTION_GPU_API.md §1.1): papers is []string —
        # each paper object serialized to a JSON string; the proxy layer
        # json.loads-escapes them back into objects for the GPU upstream.
        "papers": [
            json.dumps(
                {"paper_id": p["paper_id"], "sentences": p["sentences"]},
                ensure_ascii=False,
            )
            for p in papers
        ],
        "threshold": threshold,
        "batch_size": batch_size,
    }

    last_exc: Exception | None = None
    start = time.perf_counter()
    for attempt in range(retries + 1):
        try:
            response = requests.post(
                f"{url}/filter/batch", json=payload, timeout=timeout,
                headers=gateway_headers(),
            )
            response.raise_for_status()
            elapsed = time.perf_counter() - start
            data = response.json()
            # Online gateway envelope: {code, success, msg, data} with the
            # same papers payload under data. code!=200 / success:false /
            # data:null is a service-side error — never a silent empty batch.
            if isinstance(data, dict) and "code" in data and "papers" not in data:
                if data.get("code") != 200 or not data.get("success") or data.get("data") is None:
                    raise RuntimeError(
                        f"BERT /filter/batch gateway error: code={data.get('code')} "
                        f"msg={data.get('msg')!r}"
                    )
                data = data["data"]
            data["client_elapsed_sec"] = round(elapsed, 4)
            if attempt > 0:
                logger.warning(
                    "filter_papers_batch succeeded on attempt %d/%d after retry",
                    attempt + 1, retries + 1,
                )
            return data
        except requests.HTTPError:
            # 4xx / 5xx from server — not a transient network issue, do not retry.
            raise
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt < retries:
                backoff = _BACKOFF_BASE_SEC * (2 ** attempt)
                logger.warning(
                    "filter_papers_batch attempt %d/%d failed (%s); retrying in %.1fs",
                    attempt + 1, retries + 1, type(exc).__name__, backoff,
                )
                time.sleep(backoff)
            else:
                logger.error(
                    "filter_papers_batch exhausted %d retries: %s",
                    retries, exc,
                )

    # All retries exhausted — re-raise the last transient exception.
    assert last_exc is not None
    raise last_exc
