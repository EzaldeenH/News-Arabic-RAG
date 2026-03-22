"""
Ingestion router for the Arabic QA API.
Handles data ingestion requests.
"""
from fastapi import APIRouter, HTTPException
from app.models.schemas import IngestionRequest, IngestionResponse, ErrorResponse
from app.services.data_ingestion import DataIngestor

router = APIRouter(prefix="/api/v1", tags=["Ingestion"])

# Singleton DataIngestor instance
_ingestor: DataIngestor = None


def get_ingestor() -> DataIngestor:
    """Get or create DataIngestor instance."""
    global _ingestor
    if _ingestor is None:
        _ingestor = DataIngestor()
    return _ingestor


@router.post(
    "/ingest",
    response_model=IngestionResponse,
    responses={500: {"model": ErrorResponse}}
)
async def ingest_endpoint(request: IngestionRequest):
    """
    Ingest content from a URL into the vector database.
    
    - **url**: URL to scrape and ingest
    - **region**: Region tag for metadata (default: "Middle East")
    - **category**: Category tag for metadata (default: "News")
    
    Returns ingestion statistics.
    """
    try:
        ingestor = get_ingestor()
        
        result = ingestor.ingest(
            url=request.url,
            region=request.region,
            category=request.category
        )
        
        return IngestionResponse(
            status=result["status"],
            chunks_processed=result["chunks_processed"],
            entities_extracted=result["entities_extracted"],
            url=result["url"]
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error ingesting data: {str(e)}"
        )
