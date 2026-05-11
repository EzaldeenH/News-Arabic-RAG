"""
Pydantic schemas for the Arabic QA API.
Defines request/response contracts with support for metadata filtering.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class QueryFilters(BaseModel):
    """Optional filters for RAG query metadata filtering."""
    main_category: Optional[str] = Field(
        default=None,
        description="Main category filter (e.g., 'أخبار', 'اقتصاد')"
    )
    subcategory: Optional[str] = Field(
        default=None,
        description="Subcategory filter (e.g., 'سياسة', 'عربي')"
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
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=20,
        description="Number of top results to retrieve. If not provided, uses server default."
    )


class SourceDocument(BaseModel):
    """Represents a source document used in the answer."""
    url: str = Field(..., description="Source URL")
    title: str = Field(..., description="Document title")
    main_category: Optional[str] = Field(None, description="Main category metadata")
    subcategory: Optional[str] = Field(None, description="Subcategory metadata")
    author: Optional[str] = Field(None, description="Article author")
    date: Optional[str] = Field(None, description="Publication date")
    source: Optional[str] = Field("Al Jazeera Arabic", description="Source name")


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
        description="URL to scrape and ingest",
        examples=["https://www.aljazeera.net/where/mideast/arab/"]
    )
    main_category: Optional[str] = Field(
        default="أخبار",
        description="Main category tag for the content"
    )
    subcategory: Optional[str] = Field(
        default="عربي",
        description="Subcategory tag for the content"
    )


class IngestionResponse(BaseModel):
    """Response schema for the /api/v1/ingest endpoint."""
    status: str = Field(..., description="Ingestion status")
    chunks_processed: int = Field(..., description="Number of chunks processed")
    entities_extracted: int = Field(..., description="Number of entities extracted")
    url: str = Field(..., description="Processed URL")


class ScrapeRequest(BaseModel):
    """Request schema for the /api/v1/scrape endpoint (bulk Al Jazeera scrape)."""
    max_articles_per_section: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum articles to scrape per subcategory page"
    )
    categories: Optional[List[str]] = Field(
        default=None,
        description="Main categories to scrape (Arabic: أخبار, اقتصاد, رأي, ميدان, متخصصة, محليات). "
                    "If null, scrapes all categories.",
        examples=[["أخبار", "اقتصاد"]]
    )


class ScrapeResponse(BaseModel):
    """Response schema for the /api/v1/scrape endpoint."""
    status: str = Field(..., description="Scrape status")
    articles_scraped: int = Field(..., description="Total articles scraped")
    articles_ingested: int = Field(..., description="Articles successfully ingested into vector DB")
    chunks_processed: int = Field(..., description="Total chunks stored")
    entities_extracted: int = Field(..., description="Total entities extracted")
    sections_scraped: int = Field(..., description="Number of subcategory sections scraped")


class ClearDBResponse(BaseModel):
    """Response schema for the /api/v1/clear endpoint."""
    status: str = Field(..., description="Clear status")
    collections_deleted: List[str] = Field(
        default_factory=list,
        description="Names of deleted collections"
    )


class DBStatsResponse(BaseModel):
    """Response schema for the /api/v1/stats endpoint."""
    status: str = Field(..., description="Status")
    collection_name: str = Field(..., description="Collection name")
    total_points: int = Field(..., description="Total vectors stored")
    collection_exists: bool = Field(..., description="Whether the collection exists")


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
