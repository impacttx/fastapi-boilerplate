from typing import Any, ClassVar

from fastapi import FastAPI, status
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError


class ValidationErrorDetail(BaseModel):
    location: str
    message: str
    error_type: str
    context: dict[str, Any] | None = None


class APIValidationError(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        title="APIValidationError",
        from_attributes=True,
        json_schema_extra={
            "example": {
                "errors": [
                    {
                        "location": "body -> url",
                        "message": "invalid or missing URL scheme",
                        "error_type": "value_error.url.scheme",
                        "context": {"allowed_schemes": ["http", "https"]},
                    },
                ],
            },
        },
    )

    errors: list[ValidationErrorDetail]

    @classmethod
    def from_pydantic(cls, exc: ValidationError | RequestValidationError) -> APIValidationError:
        return cls(
            errors=[
                ValidationErrorDetail(
                    location=" -> ".join(map(str, err["loc"])),
                    message=err["msg"],
                    error_type=err["type"],
                    context=err.get("ctx"),
                )
                for err in exc.errors()
            ],
        )


class CommonHTTPError(BaseModel):
    """JSON response model for errors raised by :class:`starlette.HTTPException`."""

    message: str
    extra: dict[str, Any] | None = None


class AccessTokenRequired(Exception):
    """User has provided a refresh token when an access token is needed"""


class InvalidToken(Exception):
    """User has provided an invalid or expired token"""


class RefreshTokenRequired(Exception):
    """User has provided an access token when a refresh token is needed"""


def register_all_errors(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            content={
                "message": exc.detail,
                "error_code": "http_exception",
                "resolution": "Please refer to the 'detail' field for more information",
            },
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(AccessTokenRequired)
    async def access_token_required_exception_handler(
        _,
        exc: AccessTokenRequired,
    ) -> JSONResponse:
        return JSONResponse(
            content={
                "message": "Access token is required",
                "error_code": "access_token_required",
                "resolution": "Please provide a valid access token",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(InvalidToken)
    async def invalid_token_exception_handler(
        _,
        exc: InvalidToken,
    ) -> JSONResponse:
        return JSONResponse(
            content={
                "message": "Invalid or expired token",
                "error_code": "invalid_token",
                "resolution": "Please provide a valid token",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(RefreshTokenRequired)
    async def refresh_token_required_exception_handler(
        _,
        exc: RefreshTokenRequired,
    ) -> JSONResponse:
        return JSONResponse(
            content={
                "message": "Refresh token is required",
                "error_code": "refresh_token_required",
                "resolution": "Please provide a valid refresh token",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        _,
        exc: Exception,
    ) -> JSONResponse:
        return JSONResponse(
            content={
                "message": "An unexpected error occurred",
                "error_code": "internal_server_error",
                "resolution": "Please try again later",
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
