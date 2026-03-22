"""
Pydantic schemas for the Arabic QA API.
Defines request/response contracts with support for metadata filtering.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class QueryFilters(BaseModel):
    """Optional filters for RAG query metadata filtering."""
    region: Optional[str] = Field(
        default="Middle East",
        description="Geographic region filter (e.g., 'Middle East', 'North Africa')"
    )
    category: Optional[str] = Field(
        default="News",
        description="Content category filter (e.g., 'News', 'Economy', 'Sports')"
    )


class QueryRequest(BaseModel):
    """Request schema for the /api/v1/query endpoint."""
    question: str = Field(
        ...,
        description="The Arabic question to answer",
        examples=["ما هو تأثير القرار الأخير على السوق السعودي؟"]
    )
    filters: Optional[QueryFilters] = Field(
        default_factory=QueryFilters,
        description="Optional metadata filters for vector search"
    )
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of top results to retrieve from vector DB"
    )


class SourceDocument(BaseModel):
    """Represents a source document used in the answer."""
    url: str = Field(..., description="Source URL")
    title: str = Field(..., description="Document title")
    region: Optional[str] = Field(None, description="Region metadata")
    category: Optional[str] = Field(None, description="Category metadata")


class QueryResponse(BaseModel):
    """Response schema for the /api/v1/query endpoint."""
    answer: str = Field(
        ...,
        description="The generated Arabic answer"
    )
    sources: List[SourceDocument] = Field(
        default_factory=list,
        description="List of source documents used"
    )
    entities_found: List[str] = Field(
        default_factory=list,
        description="Named entities found in the context (LOC, ORG, PER)"
    )
    latency_ms: int = Field(
        ...,
        description="Total query latency in milliseconds"
    )
    query_id: Optional[str] = Field(
        None,
        description="Optional query ID for tracking"
    )


class HealthResponse(BaseModel):
    """Response schema for the /api/v1/health endpoint."""
    status: str = Field(..., description="Health status")
    services: Dict[str, str] = Field(
        ...,
        description="Status of dependent services"
    )


class IngestionRequest(BaseModel):
    """Request schema for the /api/v1/ingest endpoint."""
    url: str = Field(
        ...,
        description="URL to scrape and ingest"
    )
    region: Optional[str] = Field(
        default="Middle East",
        description="Region tag for the content"
    )
    category: Optional[str] = Field(
        default="News",
        description="Category tag for the content"
    )


class IngestionResponse(BaseModel):
    """Response schema for the /api/v1/ingest endpoint."""
    status: str = Field(..., description="Ingestion status")
    chunks_processed: int = Field(..., description="Number of chunks processed")
    entities_extracted: int = Field(..., description="Number of entities extracted")
    url: str = Field(..., description="Processed URL")


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
