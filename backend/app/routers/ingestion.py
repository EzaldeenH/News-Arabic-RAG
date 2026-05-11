"""
Ingestion router for the Arabic QA API.
Handles data ingestion, bulk scraping, and vector DB management.
"""
import logging
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    IngestionRequest, IngestionResponse,
    ScrapeRequest, ScrapeResponse,
    ClearDBResponse, DBStatsResponse,
    ErrorResponse,
)
from app.services.data_ingestion import DataIngestor, ArabicTextNormalizer, EntityExtractor
from app.services.scrapers.aljazeera import AlJazeeraScraper, ArabicNewsScraper, ALJAZEERA_SECTIONS
from app.core.config import settings
from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Ingestion"])

# Singleton DataIngestor instance
_ingestor: DataIngestor = None


def get_ingestor() -> DataIngestor:
    """Get or create DataIngestor instance."""
    global _ingestor
    if _ingestor is None:
        _ingestor = DataIngestor()
    return _ingestor


def _get_qdrant_client() -> QdrantClient:
    """Create a Qdrant client for DB management operations."""
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


# ─── Single URL Ingestion ────────────────────────────────────────────

@router.post(
    "/ingest",
    response_model=IngestionResponse,
    responses={500: {"model": ErrorResponse}},
)
async def ingest_endpoint(request: IngestionRequest):
    """
    Ingest content from a single URL into the vector database.

    - **url**: URL to scrape and ingest (e.g. an Al Jazeera article)
    - **main_category**: Main category tag for metadata (default: "أخبار")
    - **subcategory**: Subcategory tag for metadata (default: "عربي")

    Returns ingestion statistics.
    """
    try:
        ingestor = get_ingestor()

        result = ingestor.ingest(
            url=request.url,
            main_category=request.main_category,
            subcategory=request.subcategory,
        )

        return IngestionResponse(
            status=result["status"],
            chunks_processed=result["chunks_processed"],
            entities_extracted=result["entities_extracted"],
            url=result["url"],
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error ingesting data: {str(e)}",
        )


# ─── Bulk Al Jazeera Scrape ──────────────────────────────────────────

@router.post(
    "/scrape",
    response_model=ScrapeResponse,
    responses={500: {"model": ErrorResponse}},
)
async def scrape_endpoint(request: ScrapeRequest):
    """
    Bulk-scrape Al Jazeera Arabic and ingest into the vector database.

    Navigates all main categories and their subcategories, enters each
    article to extract full body text, then stores in the vector DB.

    - **max_articles_per_section**: Max articles per subcategory page (default: 10)
    - **categories**: Optional list of main categories to scrape
      (Arabic: أخبار, اقتصاد, رأي, ميدان, متخصصة, محليات).
      If null, scrapes all categories.

    Available categories and their subcategories:
    - **أخبار** (News): عربي, دولي, سياسة, مراسلو الجزيرة, صحافة, تحقق, وسم, موسوعة, حريات, بالصور
    - **اقتصاد** (Economy): main, عربي, دولي, أسواق, شخصي, ريادة
    - **رأي** (Opinion): مقالات, مدونات
    - **ميدان** (Dimensions): إعلام, دراسات, تراث, سلاح, صراع, فكر ونفس, وجوه, ملفات
    - **متخصصة** (Specialized): رياضة, علوم وبيئة, صحة, تقنية, أسلوب حياة, أسرة, سفر, ثقافة, فن, منوعات
    - **محليات** (Local): فلسطين, اليمن, سوريا, السودان, مصر, العراق, لبنان, المغرب, ليبيا
    """
    try:
        ingestor = get_ingestor()
        scraper = ArabicNewsScraper(source="aljazeera")

        # Scrape articles
        logger.info(
            f"Starting bulk scrape: max_articles={request.max_articles_per_section}, "
            f"categories={request.categories}"
        )
        articles = scraper.scrape(
            max_articles=request.max_articles_per_section,
            categories=request.categories,
        )

        if not articles:
            return ScrapeResponse(
                status="no_articles",
                articles_scraped=0,
                articles_ingested=0,
                chunks_processed=0,
                entities_extracted=0,
                sections_scraped=0,
            )

        # Count sections that were actually scraped
        sections_count = 0
        if request.categories:
            for cat in request.categories:
                if cat in ALJAZEERA_SECTIONS:
                    sections_count += len(ALJAZEERA_SECTIONS[cat]["subcategories"])
        else:
            for info in ALJAZEERA_SECTIONS.values():
                sections_count += len(info["subcategories"])

        # Ingest each article into the vector DB
        total_chunks = 0
        total_entities = 0
        ingested = 0

        for i, article in enumerate(articles, 1):
            try:
                logger.info(f"[{i}/{len(articles)}] Ingesting article: {article.get('url')} (Main Category: {article.get('main_category', 'أخبار')}, Subcategory: {article.get('subcategory', 'عربي')})")
                result = ingestor.ingest(
                    url=article.get("url", ""),
                    main_category=article.get("main_category", "أخبار"),
                    subcategory=article.get("subcategory", "عربي"),
                    title=article.get("title"),
                    content=article.get("content"),
                    author=article.get("author"),
                    date=article.get("date"),
                    source_name=article.get("source", "Al Jazeera Arabic")
                )
                total_chunks += result.get("chunks_processed", 0)
                total_entities += result.get("entities_extracted", 0)
                ingested += 1
                logger.info(f"[{i}/{len(articles)}] Success: {result.get('chunks_processed')} chunks, {result.get('entities_extracted')} entities stored.")
            except Exception as e:
                logger.error(
                    f"[{i}/{len(articles)}] Failed to ingest "
                    f"{article.get('url', '?')}: {e}"
                )
                continue

        return ScrapeResponse(
            status="success",
            articles_scraped=len(articles),
            articles_ingested=ingested,
            chunks_processed=total_chunks,
            entities_extracted=total_entities,
            sections_scraped=sections_count,
        )

    except Exception as e:
        logger.error(f"Bulk scrape error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error during bulk scrape: {str(e)}",
        )


# ─── Clear Vector Database ───────────────────────────────────────────

@router.delete(
    "/clear",
    response_model=ClearDBResponse,
    responses={500: {"model": ErrorResponse}},
)
async def clear_db_endpoint():
    """
    Clear all data from the vector database.

    Deletes all Qdrant collections, effectively resetting the knowledge base.
    The collection will be re-created automatically on the next ingestion.
    """
    try:
        client = _get_qdrant_client()
        collections = client.get_collections().collections
        deleted = []

        for col in collections:
            client.delete_collection(col.name)
            deleted.append(col.name)
            logger.info(f"Deleted collection: {col.name}")

        # Reset singleton so it re-creates collection on next use
        global _ingestor
        _ingestor = None

        return ClearDBResponse(
            status="success",
            collections_deleted=deleted,
        )

    except Exception as e:
        logger.error(f"Error clearing DB: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing vector database: {str(e)}",
        )


# ─── Vector DB Stats ─────────────────────────────────────────────────

@router.get(
    "/stats",
    response_model=DBStatsResponse,
    responses={500: {"model": ErrorResponse}},
)
async def stats_endpoint():
    """
    Get vector database statistics.

    Returns the number of stored vectors and collection info.
    """
    try:
        client = _get_qdrant_client()
        collection_name = settings.vector_collection
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]

        if collection_name in collection_names:
            info = client.get_collection(collection_name)
            return DBStatsResponse(
                status="ok",
                collection_name=collection_name,
                total_points=info.points_count,
                collection_exists=True,
            )
        else:
            return DBStatsResponse(
                status="ok",
                collection_name=collection_name,
                total_points=0,
                collection_exists=False,
            )

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting DB stats: {str(e)}",
        )
