"""
Data Ingestion Service.
Handles web scraping, text normalization, chunking, and entity extraction.
Prepared for Knowledge Graph integration.
"""
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class ArabicTextNormalizer:
    """
    Arabic text normalization utility.
    Handles Alef variations, Tashkeel, and text cleaning.
    """
    
    @staticmethod
    def normalize(text: str) -> str:
        """
        Normalize Arabic text for consistent processing.
        
        Args:
            text: Raw Arabic text
            
        Returns:
            Normalized text
        """
        # Normalize Alef variations (أ, إ, آ -> ا)
        text = re.sub(r'[أإآ]', 'ا', text)
        # Normalize Alef Maqsura (ى -> ي)
        text = re.sub(r'ى', 'ي', text)
        # Remove Tashkeel (diacritics: \u064B-\u065F)
        text = re.sub(r'[\u064B-\u065F]', '', text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Strip leading/trailing whitespace
        text = text.strip()
        return text


class EntityExtractor:
    """
    Entity extraction for Knowledge Graph preparation.
    Extracts LOC (Location), ORG (Organization), PER (Person) entities.
    
    Uses CAMeL Tools for Arabic NER when available, falls back to pattern-based.
    """
    
    # Arabic entity patterns (fallback)
    ORG_PATTERNS = [
        r'(شركة [^\s،\.]+)',
        r'(مؤسسة [^\s،\.]+)',
        r'(منظمة [^\s،\.]+)',
        r'(هيئة [^\s،\.]+)',
        r'(وزارة [^\s،\.]+)',
    ]
    
    LOC_PATTERNS = [
        r'(المملكة [^\s،\.]+)',
        r'(دولة [^\s،\.]+)',
        r'(مدينة [^\s،\.]+)',
        r'(السعودية)',
        r'(مصر)',
        r'(الإمارات)',
        r'(قطر)',
        r'(الكويت)',
        r'(البحرين)',
        r'(عمان)',
        r'(الأردن)',
        r'(لبنان)',
        r'(فلسطين)',
        r'(سوريا)',
        r'(العراق)',
        r'(اليمن)',
        r'(إيران)',
        r'(تركيا)',
    ]
    
    PER_PATTERNS = [
        r'(السيد [^\s،\.]+)',
        r'(الشيخ [^\s،\.]+)',
        r'(الرئيس [^\s،\.]+)',
        r'(الملك [^\s،\.]+)',
        r'(الأمير [^\s،\.]+)',
    ]
    
    def __init__(self, use_camel: bool = True):
        self.use_camel = use_camel
        self._ner_tagger = None
        self._init_camel()
    
    def _init_camel(self) -> None:
        """Initialize CAMeL Tools NER tagger if available."""
        if not self.use_camel:
            return
        try:
            from camel_tools.ner import NERecognizer
            self._ner_tagger = NERecognizer()
        except ImportError:
            self.use_camel = False
        except Exception:
            self.use_camel = False
    
    def _extract_with_camel(self, text: str) -> List[Dict[str, str]]:
        """Extract entities using CAMeL Tools."""
        if not self._ner_tagger:
            return []
        
        try:
            # CAMeL Tools returns BIO tags
            tokens = text.split()
            ner_tags = self._ner_tagger.predict(text)
            
            entities = []
            current_entity = None
            current_value = []
            
            for i, (token, tag) in enumerate(zip(tokens, ner_tags)):
                if tag.startswith('B-'):
                    # Save previous entity
                    if current_entity and current_value:
                        entities.append({
                            "type": current_entity,
                            "value": ' '.join(current_value)
                        })
                    # Start new entity
                    current_entity = tag[2:]  # Remove 'B-' prefix
                    current_value = [token]
                elif tag.startswith('I-') and current_entity:
                    current_value.append(token)
                else:
                    # End of entity
                    if current_entity and current_value:
                        entities.append({
                            "type": current_entity,
                            "value": ' '.join(current_value)
                        })
                    current_entity = None
                    current_value = []
            
            # Don't forget last entity
            if current_entity and current_value:
                entities.append({
                    "type": current_entity,
                    "value": ' '.join(current_value)
                })
            
            return entities
        except Exception:
            return []
    
    def _extract_with_patterns(self, text: str) -> List[Dict[str, str]]:
        """Extract entities using regex patterns (fallback)."""
        entities = []
        
        # Extract organizations
        for pattern in self.ORG_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                entities.append({"type": "ORG", "value": match})
        
        # Extract locations
        for pattern in self.LOC_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                entities.append({"type": "LOC", "value": match})
        
        # Extract persons
        for pattern in self.PER_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                entities.append({"type": "PER", "value": match})
        
        return entities
    
    def extract(self, text: str) -> List[Dict[str, str]]:
        """
        Extract named entities from text.
        Uses CAMeL Tools if available, otherwise falls back to patterns.
        
        Args:
            text: Arabic text
            
        Returns:
            List of entities with type and value
        """
        if self.use_camel:
            entities = self._extract_with_camel(text)
            if entities:
                return entities
        
        # Fallback to pattern-based extraction
        return self._extract_with_patterns(text)
    
    def extract_values(self, text: str) -> List[str]:
        """Extract just the entity values as a list."""
        entities = self.extract(text)
        return list(set([e["value"] for e in entities]))


class TextChunker:
    """
    Text chunking utility for RAG.
    Splits text into overlapping chunks for better retrieval.
    """
    
    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def chunk(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: Input text
            
        Returns:
            List of text chunks
        """
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            
            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk.rfind('.')
                last_arabic_period = chunk.rfind('۔')
                break_point = max(last_period, last_arabic_period)
                
                if break_point > self.chunk_size // 2:
                    chunk = chunk[:break_point + 1]
                    end = start + break_point + 1
            
            chunks.append(chunk.strip())
            start = end - self.overlap if end < len(text) else len(text)
        
        return chunks if chunks else [text]


class DataIngestor:
    """
    Main data ingestion class.
    Scrapes, normalizes, chunks, and stores data in vector DB.
    """
    
    def __init__(self):
        self.qdrant_client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port
        )
        self.embedding_model = SentenceTransformer(settings.embedding_model)
        self.normalizer = ArabicTextNormalizer()
        self.entity_extractor = EntityExtractor()
        self.chunker = TextChunker(
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap
        )
        self.collection_name = settings.vector_collection
    
    def _ensure_collection(self) -> None:
        """Create vector collection if it doesn't exist."""
        from qdrant_client.models import Distance, VectorParams
        
        collections = self.qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            self.qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
            )
    
    def scrape_url(self, url: str) -> str:
        """
        Scrape text content from a URL.
        
        Args:
            url: URL to scrape
            
        Returns:
            Scraped text content
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=settings.request_timeout)
        response.encoding = 'utf-8'  # Force UTF-8 encoding
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(['script', 'style']):
            script.decompose()
        
        # Get text content
        text = soup.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text
    
    def _embed_text(self, text: str) -> List[float]:
        """Generate embedding for text."""
        normalized = self.normalizer.normalize(text)
        embedding = self.embedding_model.encode(
            normalized,
            normalize_embeddings=True,
            convert_to_numpy=True
        )
        return embedding.tolist()
    
    def ingest(
        self,
        url: str,
        main_category: str = "أخبار",
        subcategory: str = "عربي",
        title: Optional[str] = None,
        content: Optional[str] = None,
        author: Optional[str] = None,
        date: Optional[str] = None,
        source_name: str = "Al Jazeera Arabic",
        extra_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Ingest content from a URL into the vector database.
        
        Args:
            url: URL to scrape and ingest
            main_category: Main category tag for metadata filtering
            subcategory: Subcategory tag for metadata filtering
            title: Optional pre-scraped title
            content: Optional pre-scraped content
            author: Optional author name
            date: Optional publication date
            source_name: Source name (default: Al Jazeera)
            extra_metadata: Any additional fields to store
            
        Returns:
            Ingestion statistics
        """
        self._ensure_collection()
        
        # Extract domain for title fallback
        domain = urlparse(url).netloc
        
        # Use provided content or scrape
        if content:
            raw_text = content
            logger.info(f"Using provided content for {url} ({len(raw_text)} chars).")
        else:
            logger.info(f"Scraping content from {url}...")
            raw_text = self.scrape_url(url)
            logger.info(f"Successfully scraped {len(raw_text)} characters.")
        
        # Use provided title or fallback
        if not title:
            # Simple title extraction from raw_text or domain
            title = f"{domain} - {url.split('/')[-1] or 'Article'}"
        
        # Normalize text
        normalized_text = self.normalizer.normalize(raw_text)
        
        # Chunk text
        chunks = self.chunker.chunk(normalized_text)
        logger.info(f"Chunked text into {len(chunks)} parts.")
        
        # Process each chunk
        total_entities = 0
        points = []
        
        for i, chunk in enumerate(chunks):
            # Extract entities for Graph readiness
            entities = self.entity_extractor.extract_values(chunk)
            total_entities += len(entities)
            
            # Generate embedding
            embedding = self._embed_text(chunk)
            
            # Build metadata payload
            payload = {
                "text": chunk,
                "url": url,
                "title": title,
                "main_category": main_category,
                "subcategory": subcategory,
                "author": author or "الجزيرة نت",
                "date": date or "",
                "source": source_name,
                "entities": entities,
                "chunk_index": i
            }
            
            # Merge extra metadata if provided
            if extra_metadata:
                payload.update(extra_metadata)
            
            points.append({
                "id": f"{domain}_{i}_{int(time.time())}",
                "vector": embedding,
                "payload": payload
            })
        
        # Store in Qdrant
        from qdrant_client.http import models
        from qdrant_client.http.models import PointStruct
        
        import uuid
        
        qdrant_points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=p["vector"],
                payload=p["payload"]
            )
            for i, p in enumerate(points)
        ]
        
        self.qdrant_client.upsert(
            collection_name=self.collection_name,
            points=qdrant_points
        )
        logger.info(f"Upserted {len(qdrant_points)} vectors into Qdrant collection '{self.collection_name}'. Total entities extracted: {total_entities}.")
        
        return {
            "status": "success",
            "url": url,
            "chunks_processed": len(chunks),
            "entities_extracted": total_entities
        }


# Import time at module level
import time
