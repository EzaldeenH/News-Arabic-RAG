#!/usr/bin/env python3
"""
Data Ingestion CLI Script.
Ingests Arabic news articles into the vector database.

Usage:
    python ingest.py --source aljazeera --max-articles 10
    python ingest.py --url https://www.aljazeera.net/news/2026/5/10/article-slug
    python ingest.py --batch urls.txt
"""
import argparse
import logging
import sys
import os
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_ingestion import DataIngestor, ArabicTextNormalizer, EntityExtractor
from app.services.scrapers.aljazeera import ArabicNewsScraper, AlJazeeraScraper
from app.core.config import settings

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def ingest_from_source(
    source: str,
    max_articles: int,
    main_category: str,
    subcategory: str,
    categories: Optional[List[str]] = None,
) -> dict:
    """
    Ingest articles from a news source.
    
    Args:
        source: News source name (aljazeera)
        max_articles: Maximum number of articles per subcategory to ingest
        main_category: Main category tag (overridden by auto-detection)
        subcategory: Subcategory tag (overridden by auto-detection)
        categories: Optional list of main categories to scrape
        
    Returns:
        Ingestion statistics
    """
    logger.info(f"Starting ingestion from {source} (max: {max_articles} articles per subcategory)")
    
    ingestor = DataIngestor()
    scraper = ArabicNewsScraper(source=source)
    
    articles = scraper.scrape(max_articles=max_articles, categories=categories)
    
    if not articles:
        logger.warning("No articles found")
        return {"articles": 0, "chunks": 0, "entities": 0}
    
    total_chunks = 0
    total_entities = 0
    
    for i, article in enumerate(articles, 1):
        logger.info(f"[{i}/{len(articles)}] Processing: {article.get('title', 'Unknown')}")
        
        try:
            # Combine title and content
            text = f"{article.get('title', '')}\n\n{article.get('content', '')}"
            
            # Normalize text
            normalizer = ArabicTextNormalizer()
            normalized_text = normalizer.normalize(text)
            
            # Extract entities for display
            extractor = EntityExtractor()
            entities = extractor.extract_values(normalized_text)
            
            # Use auto-detected metadata from the article, fallback to CLI args
            art_main = article.get("main_category", main_category)
            art_sub = article.get("subcategory", subcategory)

            # Store in vector DB
            result = ingestor.ingest(
                url=article.get('url', ''),
                main_category=art_main,
                subcategory=art_sub,
                title=article.get('title'),
                content=article.get('content'),
                author=article.get('author'),
                date=article.get('date'),
                source_name=article.get('source', 'Al Jazeera Arabic')
            )
            
            total_chunks += result.get('chunks_processed', 0)
            total_entities += result.get('entities_extracted', 0)
            
            logger.info(f"  -> Chunks: {result.get('chunks_processed')}, Entities: {len(entities)}")
            
        except Exception as e:
            logger.error(f"  -> Error: {e}")
            continue
    
    return {
        "articles": len(articles),
        "chunks": total_chunks,
        "entities": total_entities
    }


def ingest_url(
    url: str,
    main_category: str,
    subcategory: str
) -> dict:
    """
    Ingest a single URL.
    
    Args:
        url: URL to ingest
        main_category: Main category tag
        subcategory: Subcategory tag
        
    Returns:
        Ingestion statistics
    """
    logger.info(f"Ingesting URL: {url}")
    
    ingestor = DataIngestor()
    
    try:
        result = ingestor.ingest(url=url, main_category=main_category, subcategory=subcategory)
        logger.info(f"Successfully ingested: {result}")
        return result
    except Exception as e:
        logger.error(f"Error ingesting URL: {e}")
        return {"error": str(e)}


def ingest_batch(
    file_path: str,
    main_category: str,
    subcategory: str
) -> dict:
    """
    Ingest URLs from a file (one URL per line).
    
    Args:
        file_path: Path to file containing URLs
        main_category: Main category tag
        subcategory: Subcategory tag
        
    Returns:
        Ingestion statistics
    """
    logger.info(f"Batch ingestion from: {file_path}")
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return {"error": "File not found"}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    logger.info(f"Found {len(urls)} URLs to process")
    
    results = []
    for i, url in enumerate(urls, 1):
        logger.info(f"[{i}/{len(urls)}] Processing: {url}")
        result = ingest_url(url, main_category, subcategory)
        results.append(result)
    
    return {
        "total_urls": len(urls),
        "successful": sum(1 for r in results if 'error' not in r),
        "failed": sum(1 for r in results if 'error' in r),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Arabic news articles into the vector database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --source aljazeera --max-articles 10
  %(prog)s --source aljazeera --max-articles 5 --categories أخبار اقتصاد
  %(prog)s --url https://www.aljazeera.net/news/2026/5/10/article-slug
  %(prog)s --batch urls.txt --main-category "أخبار" --subcategory "عربي"
        """
    )
    
    # Source options (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--source",
        type=str,
        choices=["aljazeera"],
        help="News source to scrape"
    )
    source_group.add_argument(
        "--url",
        type=str,
        help="Single URL to ingest"
    )
    source_group.add_argument(
        "--batch",
        type=str,
        help="File containing URLs (one per line)"
    )
    
    # Options
    parser.add_argument(
        "--max-articles",
        type=int,
        default=10,
        help="Maximum number of articles per subcategory to scrape (default: 10)"
    )
    parser.add_argument(
        "--main-category",
        type=str,
        default="أخبار",
        help="Main category tag for metadata (default: 'أخبار')"
    )
    parser.add_argument(
        "--subcategory",
        type=str,
        default="عربي",
        help="Subcategory tag for metadata (default: 'عربي')"
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        type=str,
        default=None,
        help="Main categories to scrape (Arabic: أخبار اقتصاد رأي ميدان متخصصة محليات)"
    )
    
    args = parser.parse_args()
    
    # Print configuration
    print(f"""
╔══════════════════════════════════════════════════════════╗
║       Al Jazeera Arabic QA - Data Ingestion              ║
╠══════════════════════════════════════════════════════════╣
║  Main Cat:  {args.main_category:<42} ║
║  Subcat:    {args.subcategory:<42} ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Run ingestion
    if args.source:
        stats = ingest_from_source(
            source=args.source,
            max_articles=args.max_articles,
            main_category=args.main_category,
            subcategory=args.subcategory,
            categories=args.categories,
        )
    elif args.url:
        stats = ingest_url(
            url=args.url,
            main_category=args.main_category,
            subcategory=args.subcategory
        )
    elif args.batch:
        stats = ingest_batch(
            file_path=args.batch,
            main_category=args.main_category,
            subcategory=args.subcategory
        )
    else:
        parser.print_help()
        return 1
    
    # Print summary
    print("\n" + "=" * 50)
    print("INGESTION COMPLETE")
    print("=" * 50)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print("=" * 50)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
