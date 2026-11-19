"""Every error leaves the API as the contract's ErrorResponse: {"error": {"code", "message"}}."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

CODES = {400: "bad_request", 401: "unauthorized", 404: "not_found", 405: "method_not_allowed",
         409: "conflict", 422: "validation_failed", 500: "internal", 502: "upstream_failed", 503: "unavailable"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def error_response(status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(error_body(code, message), status_code=status, headers=headers)


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        return error_response(exc.status_code, CODES.get(exc.status_code, "error"), str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        parts = []
        for err in exc.errors()[:10]:
            loc = "/".join(str(x) for x in err.get("loc", ()) if x != "body")
            parts.append(f"{loc or 'body'}: {err.get('msg')}")
        return error_response(422, "validation_failed", "; ".join(parts) or "invalid request")
