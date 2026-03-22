#!/usr/bin/env python3
"""
Data Ingestion CLI Script.
Ingests Arabic news articles into the vector database.

Usage:
    python ingest.py --source reuters --max-articles 10
    python ingest.py --url https://www.reuters.com/world/middle-east/article
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
from app.services.scrapers.reuters import ArabicNewsScraper, ReutersScraper
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def ingest_from_source(
    source: str,
    max_articles: int,
    region: str,
    category: str
) -> dict:
    """
    Ingest articles from a news source.
    
    Args:
        source: News source name (reuters, alarabiya, etc.)
        max_articles: Maximum number of articles to ingest
        region: Region tag
        category: Category tag
        
    Returns:
        Ingestion statistics
    """
    logger.info(f"Starting ingestion from {source} (max: {max_articles} articles)")
    
    ingestor = DataIngestor()
    scraper = ArabicNewsScraper(source=source)
    
    articles = scraper.scrape(max_articles=max_articles)
    
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
            
            # Store in vector DB
            result = ingestor.ingest(
                url=article.get('url', ''),
                region=region,
                category=category
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
    region: str,
    category: str
) -> dict:
    """
    Ingest a single URL.
    
    Args:
        url: URL to ingest
        region: Region tag
        category: Category tag
        
    Returns:
        Ingestion statistics
    """
    logger.info(f"Ingesting URL: {url}")
    
    ingestor = DataIngestor()
    
    try:
        result = ingestor.ingest(url=url, region=region, category=category)
        logger.info(f"Successfully ingested: {result}")
        return result
    except Exception as e:
        logger.error(f"Error ingesting URL: {e}")
        return {"error": str(e)}


def ingest_batch(
    file_path: str,
    region: str,
    category: str
) -> dict:
    """
    Ingest URLs from a file (one URL per line).
    
    Args:
        file_path: Path to file containing URLs
        region: Region tag
        category: Category tag
        
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
        result = ingest_url(url, region, category)
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
  %(prog)s --source reuters --max-articles 10
  %(prog)s --url https://www.reuters.com/world/middle-east/article
  %(prog)s --batch urls.txt --region "Middle East" --category "News"
        """
    )
    
    # Source options (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--source",
        type=str,
        choices=["reuters", "reuters_arabic"],
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
        help="Maximum number of articles to scrape (default: 10)"
    )
    parser.add_argument(
        "--region",
        type=str,
        default="Middle East",
        help="Region tag for metadata (default: 'Middle East')"
    )
    parser.add_argument(
        "--category",
        type=str,
        default="News",
        help="Category tag for metadata (default: 'News')"
    )
    
    args = parser.parse_args()
    
    # Print configuration
    print(f"""
╔══════════════════════════════════════════════════════════╗
║           Arabic QA System - Data Ingestion              ║
╠══════════════════════════════════════════════════════════╣
║  Region:    {args.region:<42} ║
║  Category:  {args.category:<42} ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Run ingestion
    if args.source:
        stats = ingest_from_source(
            source=args.source,
            max_articles=args.max_articles,
            region=args.region,
            category=args.category
        )
    elif args.url:
        stats = ingest_url(
            url=args.url,
            region=args.region,
            category=args.category
        )
    elif args.batch:
        stats = ingest_batch(
            file_path=args.batch,
            region=args.region,
            category=args.category
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
