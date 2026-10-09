"""API privacy tests: the public endpoint must never leak a contact field.

The handler is exercised with a fake DynamoDB table so no AWS call is made. The
fake STATE item deliberately contains principal_email and a nested contact block:
if either survives into the response, the test fails. This is the guard that a
future field added to the table cannot leak by accident.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import lambda_api  # noqa: E402


class FakeTable:
    """Minimal DynamoDB stand-in: returns a STATE item and a READING item that
    both carry contact fields, so the handler must actively strip them."""

    def get_item(self, Key):  # noqa: N803 (boto3 signature)
        return {"Item": {
            "PK": Key["PK"], "SK": "STATE",
            "tier": 2, "band": "poor", "aqi": 250.0,
            "prev_tier": 1, "pending_tier": None, "pending_count": 0,
            "stale_input": False, "breakpoint_version": "cpcb-naqi-2014-pm-v1",
            # planted private fields that must NOT reach the response
            "principal_email": "principal@school.example",
            "phone": "+91-99999-00000",
            "contact": {"name": "A Principal", "email": "a@school.example"},
        }}

    def query(self, **kwargs):  # noqa: N803
        return {"Items": [{
            "PK": "SCHOOL#sch-001", "SK": "READING#2026-10-09T03:00",
            "timestamp_utc": "2026-10-09T03:00",
            "pm2_5": 79.4, "pm10": 123.9, "aqi": 162.4,
            "dominant_pollutant": "pm10", "source": "open-meteo-cams",
            "modeled": True, "stale": False, "breakpoint_version": "cpcb-naqi-2014-pm-v1",
            # planted private field on the reading too
            "principal_email": "principal@school.example",
        }]}


@pytest.fixture
def handler(monkeypatch):
    monkeypatch.setenv("DASHBOARD_ORIGIN", "https://saans.langersword.in")
    monkeypatch.setattr(lambda_api, "_table", lambda: FakeTable())
    return lambda_api.handler


def _body(resp):
    return json.loads(resp["body"])


def _walk_strings(obj):
    """Yield every string value, recursively, so a leaked email is caught even
    if it is nested inside a value rather than a key."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _walk_strings(x)
    elif isinstance(obj, str):
        yield obj


def test_response_never_contains_principal_email(handler):
    resp = handler({"pathParameters": {"school_id": "sch-001"}}, None)
    assert resp["statusCode"] == 200
    assert "principal@school.example" not in _walk_strings(_body(resp))
    assert "a@school.example" not in _walk_strings(_body(resp))


def test_no_forbidden_key_in_response(handler):
    body = _body(handler({"pathParameters": {"school_id": "sch-001"}}, None))
    for key in lambda_api.FORBIDDEN_FIELDS:
        assert key not in body, f"forbidden key {key!r} leaked at top level"
    assert "contact" not in body
    assert "principal_email" not in body.get("latest_reading", {})


def test_no_forbidden_key_anywhere_nested(handler):
    """A leak hidden in a nested object must also be caught."""
    body = _body(handler({"pathParameters": {"school_id": "sch-001"}}, None))

    def walk(d):
        if isinstance(d, dict):
            for k, v in d.items():
                assert k not in lambda_api.FORBIDDEN_FIELDS, f"leaked key {k!r}"
                walk(v)
        elif isinstance(d, list):
            for x in d:
                walk(x)
    walk(body)


def test_response_still_has_the_useful_fields(handler):
    """Stripping must not strip the dashboard's data."""
    body = _body(handler({"pathParameters": {"school_id": "sch-001"}}, None))
    for k in ("school_id", "tier", "band", "aqi", "advisory", "attribution", "limits"):
        assert k in body, f"useful field {k!r} was wrongly stripped"
    assert body["latest_reading"]["pm2_5"] == 79.4


def test_cors_origin_is_the_parameter_not_wildcard(handler):
    resp = handler({"pathParameters": {"school_id": "sch-001"}}, None)
    origin = resp["headers"]["Access-Control-Allow-Origin"]
    assert origin == "https://saans.langersword.in"
    assert origin != "*"


def test_cors_origin_reads_env(monkeypatch):
    monkeypatch.setenv("DASHBOARD_ORIGIN", "https://other.example")
    assert lambda_api._cors_origin() == "https://other.example"


def test_error_responses_are_also_stripped(handler):
    """The 400/404 paths must not leak either."""
    resp = handler({"pathParameters": {}}, None)
    assert resp["statusCode"] == 400
    assert "principal" not in _body(resp)


def test_forbidden_fields_list_covers_contact_variants():
    """Guard the guard: the list must name the obvious contact spellings."""
    for name in ("principal_email", "email", "phone", "contact", "address"):
        assert name in lambda_api.FORBIDDEN_FIELDS
