"""Shared data models for the validator pipeline.

Two models matter:
- ``Endpoint``: the normalized view of one OpenAPI operation, produced by
  ``spec_loader`` and consumed by every checker.
- ``Finding``: one quality issue (or pass) about an endpoint. Both the static and
  dynamic stages emit ``Finding`` objects, which is what lets a single dashboard
  render results from every source.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["info", "warn", "error"]
Status = Literal["pass", "warn", "fail"]
Source = Literal["static", "llm", "dynamic"]


class Endpoint(BaseModel):
    """A single OpenAPI operation, with all $refs already resolved."""

    method: str  # lower-case http verb, e.g. "post"
    path: str  # templated path, e.g. "/v1/orgs/{org}"
    operation_id: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    request_schema: Optional[dict[str, Any]] = None
    request_example: Optional[Any] = None
    # status code (as string) -> {"description", "schema", "example"}
    responses: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.method.upper()} {self.path}"


class Diff(BaseModel):
    """A spec-says-vs-reality comparison, rendered side-by-side in the dashboard."""

    expected: Any = None
    actual: Any = None


class Finding(BaseModel):
    """One quality observation about an endpoint."""

    endpoint: str  # Endpoint.key, e.g. "POST /v1/orgs"
    method: str
    path: str
    source: Source
    category: str  # e.g. "missing_example", "schema_mismatch", "status_mismatch"
    severity: Severity
    status: Status
    message: str
    diff: Optional[Diff] = None
    # Free-form extra context (e.g. raw request/response for dynamic findings).
    detail: dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    """The full output of one validation run — serialized to results.json."""

    module: str
    base_url: str
    generated_at: str
    endpoints_total: int
    endpoints_tested_live: int
    findings: list[Finding] = Field(default_factory=list)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {"pass": 0, "warn": 0, "fail": 0}
        for f in self.findings:
            counts[f.status] = counts.get(f.status, 0) + 1
        return counts
