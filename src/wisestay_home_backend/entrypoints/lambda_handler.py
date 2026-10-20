"""AWS Lambda entrypoint for API Gateway REST proxy (payload v1).

Handler: ``wisestay_home_backend.entrypoints.lambda_handler.handler``.  The
composition is built once per cold start.  Responses never carry a stack
trace; failures are ``application/problem+json`` from the closed X.1 table.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging

from wisestay_home_backend.domain import policy
from wisestay_home_backend.http.handlers import HomeScannerApi, Request, Response
from wisestay_home_backend.http.problem import PROBLEM_CONTENT_TYPE, problem_body

LOGGER = logging.getLogger("wisestay_home_backend.lambda")
_API: HomeScannerApi | None = None


def _api() -> HomeScannerApi:
    global _API
    if _API is None:
        from wisestay_home_backend.entrypoints.composition import build_live  # noqa: PLC0415

        _API = build_live().api
    return _API


def _to_proxy(response: Response) -> dict:
    return {"statusCode": response.status, "headers": dict(response.headers),
            "body": response.encoded().decode("utf-8"), "isBase64Encoded": False}


def _problem(code: str, request_id: str) -> dict:
    body = problem_body(code, request_id)
    return {"statusCode": body["status"],
            "headers": {"Content-Type": PROBLEM_CONTENT_TYPE, "X-Request-Id": request_id},
            "body": json.dumps(body, sort_keys=True, separators=(",", ":")),
            "isBase64Encoded": False}


def handle_event(event: dict, api: HomeScannerApi) -> dict:
    context = event.get("requestContext") or {}
    request_id = str(context.get("requestId") or "unknown")[:128]
    raw = event.get("body")
    body: bytes | None = None
    if raw is not None:
        if not isinstance(raw, str):
            return _problem("invalid_request", request_id)
        if len(raw) > policy.MAX_REQUEST_BODY_BYTES * 4 // 3 + 4:
            return _problem("limit_exceeded", request_id)
        if event.get("isBase64Encoded"):
            try:
                body = base64.b64decode(raw.encode("ascii"), validate=True)
            except (binascii.Error, ValueError, UnicodeEncodeError):
                return _problem("invalid_request", request_id)
        else:
            body = raw.encode("utf-8")
    request = Request(
        method=str(event.get("httpMethod") or ""), path=str(event.get("path") or ""),
        headers=dict(event.get("headers") or {}), query=dict(event.get("queryStringParameters") or {}),
        body=body, request_id=request_id)
    return _to_proxy(api.dispatch(request))


def handler(event, context):  # noqa: ARG001 - Lambda signature
    request_id = str(((event or {}).get("requestContext") or {}).get("requestId") or "unknown")[:128]
    try:
        api = _api()
    except Exception as exc:  # configuration or cold-start failure: no detail in the body
        LOGGER.error(json.dumps({"event": "composition_failed", "type": type(exc).__name__}))
        return _problem("dependency_unavailable", request_id)
    return handle_event(event or {}, api)
