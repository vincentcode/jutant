"""Staff feedback sent to Phoenix as a human annotation on the answer's span."""

import json

import httpx

from providers.tracing.feedback import PhoenixFeedback, phoenix_base, span_of

TRACE = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}


def phoenix(handler) -> PhoenixFeedback:
    return PhoenixFeedback("http://phoenix:6006", "s3cret", transport=httpx.MockTransport(handler))


async def test_a_rating_becomes_an_annotation_on_the_answer_s_span() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"data": []})

    await phoenix(handler).send(
        TRACE,
        staff_id="S0042",
        rating="down",
        reason="wrong_answer",
        comment="It said account 0011223344 was closed",
        feature_id="transaction_lookup",
    )

    [request] = sent
    assert request.url.path == "/v1/span_annotations" and request.url.params["sync"] == "false"
    assert request.headers["authorization"] == "Bearer s3cret"
    [annotation] = json.loads(request.content)["data"]
    assert annotation == {
        "span_id": "00f067aa0ba902b7",
        "name": "staff feedback",
        "annotator_kind": "HUMAN",
        "result": {
            "label": "down",
            "score": 0,
            "explanation": "It said account ******3344 was closed",  # masked
        },
        "metadata": {"reason": "wrong_answer", "feature": "transaction_lookup"},
        "identifier": "S0042",  # one per person: a changed rating replaces theirs
    }


async def test_an_answer_without_a_trace_sends_nothing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("nothing should be sent")

    await phoenix(handler).send({}, staff_id="S0042", rating="up")


async def test_phoenix_being_down_never_fails_the_rating() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    def refusing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    await phoenix(down).send(TRACE, staff_id="S0042", rating="up")
    await phoenix(refusing).send(TRACE, staff_id="S0042", rating="up")


def test_reading_the_span_and_phoenix_s_address() -> None:
    assert span_of(TRACE) == "00f067aa0ba902b7"
    assert span_of({"traceparent": "garbage"}) is None
    assert phoenix_base("http://phoenix:6006/v1/traces") == "http://phoenix:6006"
    assert phoenix_base("http://collector:4318/traces") is None
