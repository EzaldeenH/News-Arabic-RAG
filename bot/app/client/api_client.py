"""
HTTP Client for Backend API.
Singleton aiohttp session for efficient communication with the backend.
"""
import asyncio
from typing import Optional, Dict, Any
import httpx
import os


class BackendClient:
    """
    HTTP client for communicating with the backend API.
    Uses singleton pattern for session management.
    """
    
    _instance: Optional["BackendClient"] = None
    _client: Optional[httpx.AsyncClient] = None
    
    def __new__(cls) -> "BackendClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self.base_url = os.getenv("BACKEND_URL", "http://backend:8000")
            self.default_region = os.getenv("DEFAULT_REGION", "Middle East")
            self.timeout = 60  # seconds
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout)
            )
    
    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance._client
    
    async def query(
        self,
        question: str,
        top_k: int = 3
    ) -> Dict[str, Any]:
        """
        Send a query to the backend API.
        
        Args:
            question: The Arabic question
            top_k: Number of results to retrieve
            
        Returns:
            API response as dictionary
            
        Raises:
            httpx.HTTPError: If the request fails
        """
        client = await self.get_client()
        
        payload = {
            "question": question,
            "filters": {
                "region": self.default_region,
                "category": "News"
            },
            "top_k": top_k
        }
        
        response = await client.post(
            "/api/v1/query",
            json=payload
        )
        response.raise_for_status()
        
        return response.json()
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check backend health status.
        
        Returns:
            Health status response
        """
        client = await self.get_client()
        
        response = await client.get("/api/v1/health")
        response.raise_for_status()
        
        return response.json()
    
    @classmethod
    async def close(cls):
        """Close the HTTP client session."""
        if cls._instance and cls._instance._client:
            await cls._instance._client.aclose()
            cls._instance._client = None
