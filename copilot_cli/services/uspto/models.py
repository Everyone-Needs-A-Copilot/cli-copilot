"""Pydantic models for USPTO contract discovery."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CapturedContract(BaseModel):
    product: str
    captured_at: str
    url: str
    method: str
    request_headers: dict
    request_content_type: str | None
    request_body: Any
    response_status: int
    response_content_type: str | None
    response_headers: dict
    response_body_sample: Any
    response_body_size: int
    sample_query: str
    notes: list[str]


class ProductRecipe(BaseModel):
    product: str
    url: str
    search_selector: str | None
    submit_selector: str | None
    sample_query: str
    wait_for: str = "networkidle"
    confirmed: bool = False
