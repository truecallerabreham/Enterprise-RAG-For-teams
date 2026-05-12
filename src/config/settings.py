import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, model_validator

# Load .env from the project root (two levels up from this file: src/config/ -> project root)
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_env_path, override=True)


class Settings(BaseModel):
    workspace_root: Path = Path(".rag_workspace")
    vector_store: str = "memory"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "code_chunks"
    vector_size: int = 1024
    graph_provider: str = "memory"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    voyage_model: str = "voyage-code-3"
    llm_provider: str = "groq"
    llm_model: str = "llama-3.3-70b-versatile"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    max_file_bytes: int = 500_000
    chroma_collection: str = "code_chunks"
    cohere_model: str = "embed-english-v3.0"

    @model_validator(mode="before")
    @classmethod
    def load_from_env(cls, values: dict) -> dict:
        """Read every field from environment at instantiation time, not class-definition time."""
        mapping = {
            "workspace_root": ("RAG_WORKSPACE_ROOT", None),
            "vector_store":   ("VECTOR_STORE", "qdrant"),
            "qdrant_url":     ("QDRANT_URL", "http://localhost:6333"),
            "qdrant_collection": ("QDRANT_COLLECTION", "code_chunks"),
            "vector_size":    ("VECTOR_SIZE", "1024"),
            "graph_provider": ("GRAPH_PROVIDER", "memory"),
            "neo4j_uri":      ("NEO4J_URI", "bolt://localhost:7687"),
            "neo4j_user":     ("NEO4J_USERNAME", "neo4j"),
            "neo4j_password": ("NEO4J_PASSWORD", ""),
            "neo4j_database": ("NEO4J_DATABASE", "neo4j"),
            "voyage_model":   ("VOYAGE_MODEL", "voyage-code-3"),
            "llm_provider":   ("LLM_PROVIDER", "groq"),
            "llm_model":      ("LLM_MODEL", "llama-3.3-70b-versatile"),
            "cross_encoder_model": ("CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
            "max_file_bytes": ("MAX_FILE_BYTES", "500000"),
            "chroma_collection": ("CHROMA_COLLECTION", "code_chunks"),
            "cohere_model":   ("COHERE_MODEL", "embed-english-v3.0"),
        }
        for field, (env_key, default) in mapping.items():
            if field not in values:
                env_val = os.environ.get(env_key, default)
                if env_val is not None:
                    values[field] = env_val
        return values


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    return settings
