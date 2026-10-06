"""Staff feedback on an answer, attached to the answer's trace in the tracing backend.

`PhoenixFeedback` adds it as a human annotation on the answer's root span ("staff feedback":
thumbs up scores 1, thumbs down 0, with the reason and the comment), through Phoenix's REST
API. The staff member is its identifier, so a changed rating replaces theirs. The comment is
masked as the audit log masks text. Sending is best-effort: feedback is already stored, and a
tracing backend that is down must never fail the request.
"""

import logging
from collections.abc import Mapping
from typing import Protocol

import httpx

from core.privacy.masking import mask

logger = logging.getLogger(__name__)

ANNOTATION = "staff feedback"


class FeedbackSink(Protocol):
    async def send(
        self,
        trace_context: Mapping[str, str],
        *,
        staff_id: str,
        rating: str,
        reason: str = "",
        comment: str = "",
        feature_id: str | None = None,
    ) -> None: ...


class NoFeedbackSink:
    async def send(self, trace_context: Mapping[str, str], **_: object) -> None:
        pass


class PhoenixFeedback:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        *,
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_s, transport=transport
        )

    async def send(
        self,
        trace_context: Mapping[str, str],
        *,
        staff_id: str,
        rating: str,
        reason: str = "",
        comment: str = "",
        feature_id: str | None = None,
    ) -> None:
        span_id = span_of(trace_context)
        if span_id is None:
            return  # an answer from before tracing was on
        result: dict[str, object] = {"label": rating, "score": 1 if rating == "up" else 0}
        if comment:
            result["explanation"] = mask(comment)
        body = {
            "data": [
                {
                    "span_id": span_id,
                    "name": ANNOTATION,
                    "annotator_kind": "HUMAN",
                    "result": result,
                    "metadata": {"reason": reason, "feature": feature_id or ""},
                    "identifier": staff_id,
                }
            ]
        }
        try:
            response = await self._http.post(
                "/v1/span_annotations", params={"sync": "false"}, json=body
            )
            if response.status_code >= 400:
                logger.warning("feedback not sent to Phoenix: HTTP %s", response.status_code)
        except httpx.HTTPError as exc:
            logger.warning("feedback not sent to Phoenix: %s", type(exc).__name__)

    async def close(self) -> None:
        await self._http.aclose()


def span_of(trace_context: Mapping[str, str]) -> str | None:
    """The span id in a W3C traceparent ("00-<trace id>-<span id>-<flags>")."""
    parts = trace_context.get("traceparent", "").split("-")
    if len(parts) != 4 or len(parts[2]) != 16 or set(parts[2]) == {"0"}:
        return None
    return parts[2]


def phoenix_base(endpoint: str) -> str | None:
    """Phoenix's address, from its OTLP traces endpoint (http://phoenix:6006/v1/traces)."""
    suffix = "/v1/traces"
    return endpoint[: -len(suffix)] if endpoint.endswith(suffix) else None
