"""
FastAPI Main Application.
Arabic QA System - Middle East Focus
"""
import sys
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

from app.routers import query, ingestion, health


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Arabic QA System",
        description="Middle East-focused Arabic Question Answering System using RAG",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(query.router)
    app.include_router(ingestion.router)
    app.include_router(health.router)
    
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "service": "Arabic QA System",
            "version": "1.0.0",
            "docs": "/docs"
        }
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
