"""
Health check router for the Arabic QA API.
"""
from fastapi import APIRouter
from app.models.schemas import HealthResponse
from app.services.rag_engine import RAGEngine

router = APIRouter(prefix="/api/v1", tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Check the health status of the API and dependent services.
    
    Returns status of Qdrant (vector DB) and Ollama (LLM).
    """
    rag = RAGEngine()
    services = rag.health_check()
    
    all_healthy = all(status == "healthy" for status in services.values())
    
    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        services=services
    )
