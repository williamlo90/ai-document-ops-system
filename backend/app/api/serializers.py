from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.extraction.schemas import SCHEMA_VERSION


API_VERSION = "2026-08-05"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(ContractModel):
    status: Literal["ok"]


class ReadinessResponse(ContractModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


class RuntimeSummaryResponse(ContractModel):
    environment: str
    metrics: dict[str, int | float]


class ServiceMetadataResponse(ContractModel):
    service: Literal["invoice-review"] = "invoice-review"
    api_version: str = API_VERSION
    extraction_schema: str = SCHEMA_VERSION
    mutation_surface: Literal["none"] = "none"


class ProblemResponse(ContractModel):
    type: str
    title: str
    status: int
    detail: str
    request_id: str


class DocumentResponse(ContractModel):
    id: str
    original_filename: str
    status: str
    workspace_id: str
    size_bytes: int
