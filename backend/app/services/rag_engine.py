"""
RAG Engine Service.
Handles vector search, context retrieval, and LLM generation.
"""
import time
import re
from typing import List, Dict, Any, Optional, Tuple
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, Filter, FieldCondition, MatchValue, MatchAny
from sentence_transformers import SentenceTransformer
import requests
import json

from app.core.config import settings
from app.models.schemas import QueryFilters, SourceDocument


class RAGEngine:
    """
    RAG Engine for Arabic Question Answering.
    Supports metadata filtering for regional/category extensibility.
    """
    
    def __init__(self):
        self.qdrant_client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port
        )
        self.embedding_model = SentenceTransformer(settings.embedding_model)
        self.ollama_host = settings.ollama_host
        self.llm_model = settings.llm_model
        self.collection_name = settings.vector_collection
        
        # Ensure collection exists
        self._ensure_collection()
    
    def _ensure_collection(self) -> None:
        """Create vector collection if it doesn't exist."""
        collections = self.qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.collection_name not in collection_names:
            # BAAI/bge-m3 has 1024 dimensions
            self.qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
            )
    
    def _normalize_arabic_text(self, text: str) -> str:
        """
        Normalize Arabic text for consistent processing.
        Handles Alef variations and removes Tashkeel.
        """
        # Normalize Alef variations (أ, إ, آ -> ا)
        text = re.sub(r'[أإآ]', 'ا', text)
        # Normalize Alef Maqsura
        text = re.sub(r'ى', 'ي', text)
        # Remove Tashkeel (diacritics)
        text = re.sub(r'[\u064B-\u065F]', '', text)
        # Normalize multiple spaces
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _embed_query(self, query: str) -> List[float]:
        """Generate embedding for a query."""
        normalized = self._normalize_arabic_text(query)
        embedding = self.embedding_model.encode(
            normalized,
            normalize_embeddings=True,
            convert_to_numpy=True
        )
        return embedding.tolist()
    
    def _build_filter(self, filters: Optional[QueryFilters]) -> Optional[Filter]:
        """Build Qdrant filter from query filters."""
        if not filters:
            return None
        
        conditions = []
        if filters.main_category:
            conditions.append(
                FieldCondition(
                    key="main_category",
                    match=MatchValue(value=filters.main_category)
                )
            )
        
        if filters.subcategory:
            conditions.append(
                FieldCondition(
                    key="subcategory",
                    match=MatchValue(value=filters.subcategory)
                )
            )
        
        if conditions:
            return Filter(must=conditions)
        return None
    
    def _search_vectors(
        self,
        query_embedding: List[float],
        filters: Optional[Filter],
        top_k: int
    ) -> List[Dict[str, Any]]:
        """Search vector DB with optional metadata filtering."""
        results = self.qdrant_client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=filters,
            limit=top_k,
            with_payload=True
        )
        
        documents = []
        for result in results.points:
            payload = result.payload
            documents.append({
                "text": payload.get("text", ""),
                "url": payload.get("url", ""),
                "title": payload.get("title", ""),
                "region": payload.get("region", ""),
                "category": payload.get("category", ""),
                "entities": payload.get("entities", []),
                "score": result.score
            })
        
        return documents
    
    def _build_prompt(
        self,
        question: str,
        contexts: List[Dict[str, Any]],
        entities: List[str]
    ) -> str:
        """
        Build the RAG prompt for Ollama.
        Includes context, entities, and regional focus instructions.
        """
        context_text = "\n\n".join([
            f"السياق {i+1}:\n{doc['text']}"
            for i, doc in enumerate(contexts)
        ])
        
        entities_str = ""
        if entities:
            entities_str = f"\nالكيانات المستخرجة: {', '.join(entities)}"
        
        prompt = f"""أنت مساعد ذكي متخصص في أخبار **الشرق الأوسط** والاقتصاد الإقليمي.

السؤال: {question}

{context_text}
{entities_str}

تعليمات:
- أجب على السؤال مستخدماً المعلومات المتوفرة في السياق المقدم فقط.
- إذا كان السياق يحتوي على معلومات مفيدة أو ذات صلة بالسؤال (حتى لو كانت جزئية)، قم بصياغة إجابة منها.
- فقط إذا كان السياق لا يمت بصلة إطلاقاً للسؤال، قل 'لا أملك معلومات كافية'.
- الإجابة يجب أن تكون باللغة العربية الفصحى.
- اذكر المصادر أو أسماء الجهات عند الاقتضاء.

الإجابة:"""
        
        return prompt
    
    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama LLM for generation."""
        url = f"{self.ollama_host}/api/generate"
        payload = {
            "model": self.llm_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9
            }
        }
        

        response = requests.post(url, json=payload, timeout=settings.llm_timeout)
        response.raise_for_status()
        result = response.json()
        raw_response = result.get("response", "")
        
        # Extract and log thinking process for models like qwen3.5:9b
        think_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
        match = think_pattern.search(raw_response)
        
        if match:
            thinking_process = match.group(1).strip()
            logger.info(f"\n--- LLM Thinking Process ---\n{thinking_process}\n----------------------------\n")
            # Remove the think block from the final output
            clean_response = think_pattern.sub("", raw_response).strip()
            return clean_response
            
        return raw_response
    
    def _extract_entities_from_response(self, answer: str) -> List[str]:
        """
        Extract entities from the generated answer.
        Simple regex-based extraction for common patterns.
        TODO: Replace with CAMeL Tools or Spacy for production.
        """
        entities = []
        # Simple pattern for organization names (contains شركة، مؤسسة، etc.)
        org_patterns = [r'(شركة [^\s،\.]+)', r'(مؤسسة [^\s،\.]+)']
        for pattern in org_patterns:
            matches = re.findall(pattern, answer)
            entities.extend(matches)
        return list(set(entities))
    
    def query(
        self,
        question: str,
        filters: Optional[QueryFilters] = None,
        top_k: Optional[int] = None
    ) -> Tuple[str, List[SourceDocument], List[str], int]:
        """
        Execute a RAG query.
        
        Args:
            question: The Arabic question
            filters: Optional metadata filters
            top_k: Number of results to retrieve (uses default if None)
            
        Returns:
            Tuple of (answer, sources, entities, latency_ms)
        """
        start_time = time.time()
        
        if top_k is None:
            top_k = settings.default_top_k
        
        # Use defaults only if nothing is provided at all
        if filters is None:
            # We don't force filters anymore, allowing global search
            filters = QueryFilters()
        
        # Embed and search
        query_embedding = self._embed_query(question)
        vector_filter = self._build_filter(filters)
        documents = self._search_vectors(query_embedding, vector_filter, top_k)
        
        if not documents:
            latency_ms = int((time.time() - start_time) * 1000)
            return (
                "لا أملك معلومات كافية للإجابة على هذا السؤال.",
                [],
                [],
                latency_ms
            )
        
        # Collect all entities from documents
        all_entities = []
        for doc in documents:
            if doc.get("entities"):
                all_entities.extend(doc["entities"])
        all_entities = list(set(all_entities))
        
        # Build prompt and generate answer
        prompt = self._build_prompt(question, documents, all_entities)
        answer = self._call_ollama(prompt)
        
        # Extract additional entities from answer
        answer_entities = self._extract_entities_from_response(answer)
        all_entities = list(set(all_entities + answer_entities))
        
        # Build sources list
        sources = [
            SourceDocument(
                url=doc["url"],
                title=doc["title"],
                main_category=doc.get("main_category"),
                subcategory=doc.get("subcategory"),
                author=doc.get("author"),
                date=doc.get("date"),
                source=doc.get("source", "Al Jazeera Arabic")
            )
            for doc in documents
            if doc.get("url")
        ]
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return answer, sources, all_entities, latency_ms
    
    def health_check(self) -> Dict[str, str]:
        """Check health of dependent services."""
        services = {}
        
        # Check Qdrant
        try:
            self.qdrant_client.get_collections()
            services["qdrant"] = "healthy"
        except Exception as e:
            services["qdrant"] = f"unhealthy: {str(e)}"
        
        # Check Ollama
        try:
            response = requests.get(f"{self.ollama_host}/api/tags", timeout=5)
            if response.status_code == 200:
                services["ollama"] = "healthy"
            else:
                services["ollama"] = f"unhealthy: status {response.status_code}"
        except Exception as e:
            services["ollama"] = f"unhealthy: {str(e)}"
        
        return services
