"""
Pydantic schemas for the FastAPI request/response layer.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=300, example="graph neural networks")
    max_papers: int = Field(default=40, ge=5, le=100)
    min_year: int = Field(default=2015, ge=1990, le=2026)
    use_rebel: bool = Field(default=False, description="Run REBEL relation extraction (slower)")
    use_cache: bool = Field(default=True, description="Use cached results if available")


class JobStatus(BaseModel):
    job_id: str
    status: str          # "queued" | "running" | "done" | "error"
    progress: int        # 0-100
    current_step: str
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    logs: list[str] = Field(default_factory=list)


class PaperOut(BaseModel):
    id: int
    title: str
    year: Optional[int]
    citation_count: int
    key_contribution: Optional[str]
    method: Optional[str]
    dataset: Optional[str]
    metrics: Optional[str]
    pdf_url: Optional[str]
    cluster_id: Optional[int] = None


class ClusterOut(BaseModel):
    cluster_id: int
    label: str
    paper_count: int
    is_noise: bool


class GapOut(BaseModel):
    rank: int
    title: str
    description: str
    why_it_matters: str
    suggested_methods: str
    difficulty: str
    gap_type: str
