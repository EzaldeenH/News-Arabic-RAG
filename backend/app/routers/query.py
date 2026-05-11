"""
Query router for the Arabic QA API.
Handles question answering requests via RAG.
"""
from fastapi import APIRouter, HTTPException
from app.models.schemas import QueryRequest, QueryResponse, ErrorResponse
from app.services.rag_engine import RAGEngine

router = APIRouter(prefix="/api/v1", tags=["Query"])

# Singleton RAG engine instance
_rag_engine: RAGEngine = None


def get_rag_engine() -> RAGEngine:
    """Get or create RAG engine instance."""
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine()
    return _rag_engine


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={500: {"model": ErrorResponse}}
)
async def query_endpoint(request: QueryRequest):
    """
    Answer an Arabic question using RAG.
    
    - **question**: The Arabic question to answer
    - **filters**: Optional metadata filters (main_category, subcategory)
    - **top_k**: Number of top results to retrieve
    
    Returns the answer, sources, entities found, and latency.
    """
    try:
        rag = get_rag_engine()
        
        answer, sources, entities, latency_ms = rag.query(
            question=request.question,
            filters=request.filters,
            top_k=request.top_k
        )
        
        return QueryResponse(
            answer=answer,
            sources=sources,
            entities_found=entities,
            latency_ms=latency_ms
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing query: {str(e)}"
        )
