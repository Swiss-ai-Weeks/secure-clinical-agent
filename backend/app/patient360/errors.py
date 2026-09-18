"""Uniform error bodies (FHIR Resource Plan §4.3) and their exception handlers.

The not-found body is serialised once, at import, and served as the same bytes
for an unauthorized patient and for a nonexistent one. Nothing about the request
(patient key, reason, audit id) is echoed, so the body cannot act as an
existence oracle.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

FHIR_JSON = "application/fhir+json"
REASON_SYSTEM = "https://patient360.example/reason-codes"
AUDIT_EXTENSION = "https://patient360.example/StructureDefinition/audit-id"

NOT_FOUND_BODY = {
    "resourceType": "OperationOutcome",
    "issue": [{"severity": "error", "code": "not-found", "diagnostics": "Resource not found"}],
}
NOT_FOUND_BYTES = json.dumps(NOT_FOUND_BODY, separators=(",", ":"), sort_keys=True).encode()

TRANSIENT_BODY = {
    "resourceType": "OperationOutcome",
    "issue": [{"severity": "error", "code": "transient", "diagnostics": "Policy or audit store unavailable"}],
}
TRANSIENT_BYTES = json.dumps(TRANSIENT_BODY, separators=(",", ":"), sort_keys=True).encode()

UNAUTHENTICATED_BODY = {
    "resourceType": "OperationOutcome",
    "issue": [{"severity": "error", "code": "login", "diagnostics": "Authentication required"}],
}
UNAUTHENTICATED_BYTES = json.dumps(UNAUTHENTICATED_BODY, separators=(",", ":"), sort_keys=True).encode()


class NotFound(Exception):
    """Unauthorized or nonexistent: the caller cannot tell which."""


class Deny(Exception):
    """A deny with a visible reason (off duty, step-up, agent write)."""

    def __init__(self, reason_code: str, audit_id: UUID | None = None) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.audit_id = audit_id


class Transient(Exception):
    """Fail closed: OpenFGA or the audit store did not answer."""


class Unauthenticated(Exception):
    """No live session and no valid run token."""


class NotImplementedPath(Exception):
    """A path the plan defines but this slice does not serve (aggregate)."""

    def __init__(self, what: str, audit_id: UUID | None = None) -> None:
        super().__init__(what)
        self.what = what
        self.audit_id = audit_id


class Conflict(Exception):
    """The write names a state that already holds (consent_exists, already_revoked)."""

    def __init__(self, reason_code: str, audit_id: UUID | None = None) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.audit_id = audit_id


class Invalid(Exception):
    """A well-formed request the policy cannot accept (window too long, expiry before start)."""

    def __init__(self, reason_code: str, diagnostics: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.diagnostics = diagnostics


class Throttled(Exception):
    """Too many break-glass activations for one user."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("throttled")
        self.retry_after_seconds = retry_after_seconds


def not_found_response() -> Response:
    return Response(content=NOT_FOUND_BYTES, status_code=404, media_type=FHIR_JSON)


def transient_response() -> Response:
    return Response(content=TRANSIENT_BYTES, status_code=503, media_type=FHIR_JSON)


def unauthenticated_response() -> Response:
    return Response(content=UNAUTHENTICATED_BYTES, status_code=401, media_type=FHIR_JSON)


def deny_response(reason_code: str, audit_id: UUID | None) -> Response:
    issue: dict = {
        "severity": "error",
        "code": "security",
        "details": {"coding": [{"system": REASON_SYSTEM, "code": reason_code}]},
        "diagnostics": f"Access denied: {reason_code}",
    }
    body: dict = {"resourceType": "OperationOutcome", "issue": [issue]}
    if audit_id is not None:
        body["extension"] = [{"url": AUDIT_EXTENSION, "valueString": str(audit_id)}]
    return JSONResponse(body, status_code=403, media_type=FHIR_JSON)


def not_implemented_response(what: str, audit_id: UUID | None) -> Response:
    body: dict = {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": "error", "code": "not-supported", "diagnostics": f"Not implemented: {what}"}],
    }
    if audit_id is not None:
        body["extension"] = [{"url": AUDIT_EXTENSION, "valueString": str(audit_id)}]
    return JSONResponse(body, status_code=501, media_type=FHIR_JSON)


def _outcome(
    status: int, code: str, reason_code: str | None, diagnostics: str, audit_id: UUID | None
) -> Response:
    issue: dict = {"severity": "error", "code": code, "diagnostics": diagnostics}
    if reason_code:
        issue["details"] = {"coding": [{"system": REASON_SYSTEM, "code": reason_code}]}
    body: dict = {"resourceType": "OperationOutcome", "issue": [issue]}
    if audit_id is not None:
        body["extension"] = [{"url": AUDIT_EXTENSION, "valueString": str(audit_id)}]
    return JSONResponse(body, status_code=status, media_type=FHIR_JSON)


def conflict_response(reason_code: str, audit_id: UUID | None) -> Response:
    return _outcome(409, "conflict", reason_code, f"Conflict: {reason_code}", audit_id)


def invalid_response(reason_code: str, diagnostics: str) -> Response:
    return _outcome(422, "invalid", reason_code, diagnostics, None)


def throttled_response(retry_after_seconds: int) -> Response:
    resp = _outcome(429, "throttled", "break_glass_rate_limited", "Too many break-glass activations", None)
    resp.headers["Retry-After"] = str(retry_after_seconds)
    return resp


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(Conflict)
    async def _conflict(_: Request, exc: Conflict) -> Response:
        return conflict_response(exc.reason_code, exc.audit_id)

    @app.exception_handler(Invalid)
    async def _invalid(_: Request, exc: Invalid) -> Response:
        return invalid_response(exc.reason_code, exc.diagnostics)

    @app.exception_handler(Throttled)
    async def _throttled(_: Request, exc: Throttled) -> Response:
        return throttled_response(exc.retry_after_seconds)

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, __: NotFound) -> Response:
        return not_found_response()

    @app.exception_handler(Deny)
    async def _deny(_: Request, exc: Deny) -> Response:
        return deny_response(exc.reason_code, exc.audit_id)

    @app.exception_handler(Transient)
    async def _transient(_: Request, __: Transient) -> Response:
        return transient_response()

    @app.exception_handler(Unauthenticated)
    async def _unauthenticated(_: Request, __: Unauthenticated) -> Response:
        return unauthenticated_response()

    @app.exception_handler(NotImplementedPath)
    async def _not_implemented(_: Request, exc: NotImplementedPath) -> Response:
        return not_implemented_response(exc.what, exc.audit_id)
