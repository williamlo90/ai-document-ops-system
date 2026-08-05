from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.serializers import ProblemResponse


async def http_problem_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        raise TypeError("http_problem_handler requires HTTPException")
    request_id = str(getattr(request.state, "request_id", "unknown"))
    title = "Request failed" if exc.status_code < 500 else "Service error"
    problem = ProblemResponse(
        type=f"urn:invoice-review:http:{exc.status_code}",
        title=title,
        status=exc.status_code,
        detail=str(exc.detail),
        request_id=request_id,
    )
    return JSONResponse(status_code=exc.status_code, content=problem.model_dump())
