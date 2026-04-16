from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class BadRequestError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(400, message)


class NotFoundError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(404, message)


class ConflictError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(409, message)


class StorageError(ApiError):
    def __init__(self, message: str = "Storage operation failed.") -> None:
        super().__init__(500, message)


class TelegramOperationError(ApiError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(status_code, message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": f"Internal server error: {exc}"})

