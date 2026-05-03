import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    workspace_root: Path = Path(os.getenv("RAG_WORKSPACE_ROOT", ".rag_workspace"))
    vector_store: str = os.getenv("VECTOR_STORE", "memory")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "code_chunks")
    vector_size: int = int(os.getenv("VECTOR_SIZE", "64"))
    graph_provider: str = os.getenv("GRAPH_PROVIDER", "memory")
    voyage_model: str = os.getenv("VOYAGE_MODEL", "voyage-code-3")
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet")
    max_file_bytes: int = int(os.getenv("MAX_FILE_BYTES", "500000"))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    return settings
