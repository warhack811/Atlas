"""
Atlas Constants
---------------
Centralized constants for the application.
"""

# Models
GEMINI_FLASH_MODEL = "gemini-2.0-flash"
GEMINI_PRO_MODEL = "gemini-1.5-pro"
LLAMA_VERSATILE_MODEL = "llama-3.3-70b-versatile"
LLAMA_INSTANT_MODEL = "llama-3.1-8b-instant"
QWEN_CODER_MODEL = "qwen-2.5-coder-32b"
DEEPSEEK_R1_MODEL = "deepseek-r1-distill-llama-70b"
WHISPER_LARGE_MODEL = "whisper-large-v3-turbo"

# Collections
QDRANT_COLLECTION_NAME = "episodes"

# Timeouts
HTTP_TIMEOUT = 30.0
HTTP_LONG_TIMEOUT = 120.0

# Defaults
DEFAULT_EMBEDDING_MODEL = "text-embedding-004"
DEFAULT_MEMORY_MODE = "STANDARD"

# Environment Variables Keys
ENV_QDRANT_URL = "QDRANT_URL"
ENV_QDRANT_API_KEY = "QDRANT_API_KEY"
ENV_GEMINI_API_KEY = "GEMINI_API_KEY"
ENV_GROQ_API_KEY = "GROQ_API_KEY"
ENV_NEO4J_URI = "NEO4J_URI"
ENV_NEO4J_USER = "NEO4J_USER"
ENV_NEO4J_PASSWORD = "NEO4J_PASSWORD"
