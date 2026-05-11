"""
Core configuration for the backend service.
Loads environment variables and provides settings.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Vector DB Configuration
    qdrant_host: str = Field(default="qdrant", env="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, env="QDRANT_PORT")
    vector_collection: str = Field(default="arabic_qa_collection", env="VECTOR_COLLECTION")
    vector_db_type: str = Field(default="qdrant", env="VECTOR_DB_TYPE")

    # LLM Configuration
    ollama_host: str = Field(default="http://ollama:11434", env="OLLAMA_HOST")
    llm_model: str = Field(default="llama3.1:8b", env="LLM_MODEL")

    # Embedding Configuration
    embedding_model: str = Field(default="BAAI/bge-m3", env="EMBEDDING_MODEL")

    # Regional Configuration
    enable_graph_extract: bool = Field(default=False, env="ENABLE_GRAPH_EXTRACT")

    # Ingestion Configuration
    chunk_size: int = Field(default=500, env="CHUNK_SIZE")
    chunk_overlap: int = Field(default=50, env="CHUNK_OVERLAP")
    default_top_k: int = Field(default=5, env="DEFAULT_TOP_K")
    request_timeout: int = Field(default=30, env="REQUEST_TIMEOUT")
    llm_timeout: int = Field(default=300, env="LLM_TIMEOUT")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    class Config:
        env_file = (".env", "../.env")
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields not defined in the model

    @property
    def qdrant_url(self) -> str:
        """Get full Qdrant URL."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


# Global settings instance
settings = Settings()
