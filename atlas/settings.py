from pydantic_settings import BaseSettings
from typing import List, Dict, Optional
import os

class Settings(BaseSettings):
    # Core API Keys
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # Neo4j
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # Qdrant & Redis
    QDRANT_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # Feature Flags
    ENABLE_HYBRID_RETRIEVAL: bool = False
    ENABLE_SEMANTIC_CACHE: bool = True
    ENABLE_CONTEXT_BRIDGE: bool = False
    BYPASS_VECTOR_SEARCH: bool = False
    BYPASS_GRAPH_SEARCH: bool = False

    # Model Governance
    MODEL_GOVERNANCE: Dict[str, List[str]] = {
        "orchestrator": ["gemini-2.0-flash", "llama-3.3-70b-versatile"],
        "synthesizer": ["moonshotai/kimi-k2-instruct", "llama-3.3-70b-versatile"]
    }

    # Environment
    ENV: str = "development"
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
